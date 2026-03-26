#!/usr/bin/env python3
"""
Manage agent-cli-helper sessions across different namespaces.
"""

import argparse
import fnmatch
import os
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_socket_dir() -> str:
    """Get the tmux socket directory."""
    return "/tmp/tmux-1000"


# Namespace prefix for our sockets (cli-tool)
SOCKET_PREFIX = 'cltl'

def list_tmux_sockets() -> List[str]:
    """
    List all cli-tool tmux socket files in the socket directory.
    
    Only returns sockets starting with our prefix (cltl-) to avoid
    affecting other tmux sockets.
    
    Socket names are like "cltl-391293_codebuff" where:
    - cltl is our namespace prefix
    - 391293 is the harness PID
    - codebuff is the harness process name
    """
    socket_dir = get_socket_dir()
    if not os.path.exists(socket_dir):
        return []
    
    sockets = []
    for f in os.listdir(socket_dir):
        # Only include our prefixed sockets
        if not f.startswith(SOCKET_PREFIX + '-'):
            continue
        # Skip if it contains ':' (that's a tmux server socket with server name)
        if ':' in f:
            continue
        # This is our socket
        sockets.append(f)
    
    return sorted(sockets)


def check_process_alive(pid: int) -> bool:
    """Check if a process with given PID is still alive."""
    try:
        # Check if process exists by reading /proc/<pid>/stat
        # We just need to see if the directory exists
        return os.path.exists(f'/proc/{pid}')
    except (ValueError, OSError):
        return False


def parse_socket_name(socket_name: str) -> Tuple[Optional[int], str]:
    """
    Parse socket name like "cltl-391293_codebuff" into (pid, process_name).
    
    Returns (pid, process_name) or (None, socket_name) if can't parse.
    """
    # Strip our prefix if present
    if socket_name.startswith(SOCKET_PREFIX + '-'):
        socket_name = socket_name[len(SOCKET_PREFIX)+1:]
    
    if '_' in socket_name:
        parts = socket_name.split('_', 1)
        try:
            pid = int(parts[0])
            return pid, parts[1] if len(parts) > 1 else ''
        except ValueError:
            pass
    return None, socket_name


def run_tmux_cmd(socket_name: str, args: List[str]) -> Tuple[int, str, str]:
    """Run a tmux command on a specific socket."""
    cmd = ['tmux', '-L', socket_name] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", "tmux not found"
    except Exception as e:
        return 1, "", str(e)


def list_sessions_for_socket(socket_name: str) -> List[Dict]:
    """
    List all sessions for a given socket with their details.
    
    Returns list of dicts with: session_name, created_time, activity_time, current_program
    """
    fmt = '#{session_name} #{session_created} #{session_activity} #{pane_current_command}'
    returncode, stdout, stderr = run_tmux_cmd(socket_name, ['list-sessions', '-F', fmt])
    
    sessions = []
    if returncode != 0:
        return sessions
    
    for line in stdout.strip().split('\n'):
        if not line.strip():
            continue
        # Format: session_name created_time activity_time current_program
        parts = line.split(' ', 3)
        if len(parts) >= 3:
            try:
                sessions.append({
                    'name': parts[0],
                    'created': int(parts[1]),
                    'activity': int(parts[2]),
                    'program': parts[3] if len(parts) > 3 else 'unknown'
                })
            except (ValueError, IndexError):
                pass
    
    return sessions


def format_uptime(seconds: int) -> str:
    """Format seconds as human readable uptime."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"


def print_tree(sockets: List[str], show_all: bool = False) -> None:
    """Print the session tree."""
    current_time = int(time.time())
    
    for socket_name in sockets:
        pid, proc_name = parse_socket_name(socket_name)
        
        # Check if parent process is alive
        is_alive = False
        if pid is not None:
            is_alive = check_process_alive(pid)
        
        status = "active" if is_alive else "dead"
        
        # Format socket display (convert _ back to - for display)
        display_name = socket_name.replace('_', '-')
        
        # List sessions for this socket
        sessions = list_sessions_for_socket(socket_name)
        
        # Sort sessions by name
        sessions.sort(key=lambda s: s['name'])
        
        # Skip empty sockets unless showing all
        if not sessions and not show_all:
            continue
        
        # Print namespace header
        print(f"- {display_name}    ({status})")
        
        if not sessions:
            print("  (no sessions)")
            continue
        
        # Print sessions with tree characters
        for i, session in enumerate(sessions):
            is_last = i == len(sessions) - 1
            branch = "╰-" if is_last else "|-"
            
            # Calculate idle time
            idle_seconds = current_time - session['activity']
            idle_str = format_uptime(idle_seconds)
            
            print(f"  {branch} {session['name']}   {idle_str}")


def kill_matching_sessions(pattern: str, verbose: bool = False) -> int:
    """
    Kill sessions matching the pattern.
    
    Pattern can be:
    - "socket-name/*" - kill all sessions in a namespace
    - "*-1" - kill sessions matching pattern across all namespaces
    - "session-name" - kill specific session in current namespace
    
    Returns number of sessions killed.
    """
    sockets = list_tmux_sockets()
    killed = []
    
    for socket_name in sockets:
        sessions = list_sessions_for_socket(socket_name)
        
        for session in sessions:
            session_name = session['name']
            
            # Check if this session matches the pattern
            # Pattern format: "socket-name/*" or "session-name" or "*-1"
            
            # Convert socket display name back to socket name for matching
            socket_pattern = socket_name.replace('_', '-')
            
            # Handle glob patterns
            match = False
            
            if '/*' in pattern:
                # Kill all in namespace: "12313-codebuff/*"
                ns_pattern = pattern.replace('/*', '')
                if fnmatch.fnmatch(socket_pattern, ns_pattern):
                    match = True
            elif '-' in pattern:
                # Pattern like "*-1" - check session name
                if fnmatch.fnmatch(session_name, pattern):
                    match = True
            else:
                # Exact session name match
                if session_name == pattern:
                    match = True
            
            if match:
                # Kill the session
                returncode, stdout, stderr = run_tmux_cmd(
                    socket_name, 
                    ['kill-session', '-t', session_name]
                )
                
                if returncode == 0:
                    killed.append(f"{socket_name.replace('_', '-')}/{session_name}")
                    if verbose:
                        print(f"killed {socket_name}/{session_name}")
    
    if killed:
        print("killing")
        for k in killed:
            print(f" - {k}")
        return 0
    else:
        print("no sessions matched")
        return 1


def main():
    """Main entry point for acli-manage."""
    parser = argparse.ArgumentParser(
        description='View and manage agent-cli-helper sessions.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {version("agent-cli-helper")}')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Default: list command
    list_parser = subparsers.add_parser(
        'list',
        help='List all sessions in tree view'
    )
    list_parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Show even empty namespaces'
    )
    
    # Kill command
    kill_parser = subparsers.add_parser(
        'kill',
        help='Kill sessions matching pattern'
    )
    kill_parser.add_argument(
        'pattern',
        help='Pattern to match sessions (e.g., "namespace/*" or "*-1")'
    )
    kill_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show each killed session'
    )
    
    args = parser.parse_args()
    
    # Default command is list
    if args.command == 'kill' or (args.command is None and len(sys.argv) > 1 and sys.argv[1] == 'kill'):
        # Handle "kill" subcommand or direct pattern
        if args.command == 'kill':
            pattern = args.pattern
        else:
            # Called as "cli-manage kill <pattern>"
            pattern = sys.argv[2] if len(sys.argv) > 2 else ''
        return kill_matching_sessions(pattern, getattr(args, 'verbose', False))
    
    # List command (default)
    show_all = getattr(args, 'all', False)
    sockets = list_tmux_sockets()
    print_tree(sockets, show_all=show_all)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())