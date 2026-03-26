#!/usr/bin/env python3
"""
Examples:
    agent-cli-helper run-command <cmd>            # Run a program in a session
    agent-cli-helper send-keystrokes <id> <keys>    # Send keystrokes to a session
    agent-cli-helper process-info <id>              # Get process info for a session
    agent-cli-helper kill-all-tools                 # Kill all sessions
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional, List, Tuple




# Tip rotation state - tracks which tip was last shown (0-based index)
_last_tip_index = -1

# Configure logging - DEBUG level when LOGGING=debug
import logging
logging.basicConfig(
    level=logging.DEBUG if os.environ.get('LOGGING') == 'debug' else logging.WARNING,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Namespace prefix for our sockets (cli-tool)
SOCKET_PREFIX = 'cltl'

# Common shells to skip when walking PPID chain
SHELLS = {'bash', 'zsh', 'sh', 'dash', 'fish', 'tcsh', 'csh', 'ksh', 'ash', 'busybox'}

def get_socket_name() -> str:
    """
    Get the tmux socket name for this process.
    
    Walks up the PPID chain, skips shell processes, and returns the
    harness PID (first non-shell parent) formatted as "cltl-PID-procname".
    This ensures all processes forked from the same harness share the
    same socket, while different harness instances get different sockets.
    The "cltl-" prefix ensures we don't clash with other tmux sockets.
    """
    current_pid = os.getpid()
    depth = 0
    max_depth = 4
    
    while depth < max_depth:
        try:
            with open(f'/proc/{current_pid}/stat', 'r') as f:
                stat = f.read().split()
                ppid = int(stat[3])
        except (FileNotFoundError, IndexError, PermissionError):
            break
        
        if ppid <= 1:
            break
        
        try:
            with open(f'/proc/{ppid}/comm', 'r') as f:
                proc_name = f.read().strip()
        except (FileNotFoundError, PermissionError):
            break
        
        # If parent is a shell, keep walking up
        if proc_name.lower() in SHELLS:
            current_pid = ppid
            depth += 1
            continue
        
        # Found the harness (non-shell parent) - add our prefix
        return f"{SOCKET_PREFIX}-{ppid}_{proc_name}"
    
    # Fallback to current PID if nothing found - add our prefix
    return f"{SOCKET_PREFIX}-{os.getpid()}"


def run_tmux_cmd(args: List[str], capture: bool = True) -> Tuple[int, str, str]:
    """
    Run a command and return (returncode, stdout, stderr).
    
    Uses -L flag with PID-based socket name to ensure socket isolation.
    Each agent instance gets its own tmux socket and can't see other agents' sessions.
    """
    socket_name = get_socket_name()
    logger.debug(f"run_tmux_cmd: socket='{socket_name}', args={args}")
    
    # Ensure socket directory exists (tmux -L creates socket on first session)
    socket_dir = "/tmp/tmux-1000"
    if not os.path.exists(socket_dir):
        os.makedirs(socket_dir, exist_ok=True)
        logger.debug(f"run_tmux_cmd: created socket directory {socket_dir}")
    
    cmd = ['tmux', '-L', socket_name] + args
    logger.debug(f"run_tmux_cmd: running: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True
        )
        logger.debug(f"run_tmux_cmd: result={result.returncode}, stdout={result.stdout[:100]}, stderr={result.stderr[:100]}")
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        logger.debug("run_tmux_cmd: tmux not found")
        return 1, "", "The session manager is not available. Please install tmux or make it available in the sandbox."
    except Exception as e:
        logger.debug(f"run_tmux_cmd: exception {e}")
        return 1, "", str(e)
    
    logger.debug(f"run_tmux_cmd: result={result.returncode}, stdout={result.stdout[:100]}, stderr={result.stderr[:100]}")


def sanitize_command_name(command: str) -> str:
    """
    Sanitize command name for use in session ID.
    
    Replaces non-word characters with space, collapses multiple spaces
    to single dashes, converts to lowercase.
    Example: "vim /tmp/file.txt" -> "vim-tmp-file"
    """
    # Get the base command (first word) + first argument if exists
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return "session"
    
    # Use first word (command) + first argument
    base = cmd_parts[0].split('/')[-1]  # e.g., "vim" or "ssh"
    if len(cmd_parts) > 1:
        first_arg = cmd_parts[1]
        if '/' in first_arg:
            # It's a path - get the first directory + filename (without extension)
            # e.g., /tmp/file.txt -> tmp-file
            parts = [p for p in first_arg.split('/') if p and p != '.']
            if len(parts) >= 2:
                first_arg = f"{parts[0]}-{parts[1].rsplit('.', 1)[0]}"
            elif len(parts) == 1:
                first_arg = parts[0].rsplit('.', 1)[0]
            else:
                first_arg = "file"
        # else: first_arg stays as-is (for hostnames, etc.)
        base = f"{base}-{first_arg}"
    
    # Sanitize: replace non-word chars with space, collapse, lowercase
    sanitized = re.sub(r'\W+', ' ', base)
    sanitized = re.sub(r'\s+', '-', sanitized)
    sanitized = sanitized.lower().strip('-')
    
    return sanitized if sanitized else "session"


def get_existing_session_ids() -> List[str]:
    """Get list of existing tmux session IDs."""
    returncode, stdout, stderr = run_tmux_cmd(['list-sessions', '-F', '#{session_name}'])
    if returncode == 0 and stdout.strip():
        return [s.strip() for s in stdout.strip().split('\n') if s.strip()]
    return []


def find_matching_session(sanitized_name: str, namespace: str) -> Optional[str]:
    """Find an existing session that matches the sanitized name."""
    existing = get_existing_session_ids()
    
    # Look for session that exactly matches the sanitized name
    for session in existing:
        if session == sanitized_name:
            return session
    
    return None


def generate_session_id(command: str, namespace: Optional[str] = None, force_new: bool = False) -> Tuple[str, Optional[str]]:
    """
    Generate a session ID from the command name.
    
    Session ID is just the sanitized command name (e.g., "vim-tmp-file").
    No prefix, no UUID suffix.
    
    Returns (session_id, matching_session) where matching_session is the ID
    of an existing session if there's a collision (and force_new is False).
    """
    # Sanitize the command name
    sanitized_name = sanitize_command_name(command)
    
    # Check for collision (unless force_new is True)
    matching_session = None
    if not force_new:
        matching_session = find_matching_session(sanitized_name, namespace or 'default')
        if matching_session:
            return "", matching_session  # Signal collision
    
    # Return just the sanitized name - no prefix, no UUID
    return sanitized_name, None


def capture_pane(session_id: str) -> str:
    """Capture the current pane content."""
    logger.debug(f"capture_pane: session_id='{session_id}'")
    returncode, stdout, stderr = run_tmux_cmd([
        'capture-pane', '-t', session_id, '-p'
    ])
    if returncode == 0:
        return stdout
    logger.debug(f"capture_pane: error {returncode} - {stderr}")
    return f"<error capturing pane: {stderr}>"


def get_current_program(session_id: str) -> str:
    """
    Get the current program running in a session.
    
    Returns the program name (e.g., "vim", "ssh", "bash") from the pane's
    current command.
    """
    returncode, stdout, stderr = run_tmux_cmd([
        'list-panes', '-t', session_id, '-F', '#{pane_current_command}'
    ])
    
    if returncode == 0 and stdout.strip():
        return stdout.strip()
    return "unknown"


def new_command(command: str, force_new: bool = False) -> int:
    """
    Start a new command in a tmux session.
    
    Creates a new detached tmux session, sends the command to it,
    and returns XML output with session info and screen capture.
    
    If force_new is True and a session with the same name exists,
    adds a suffix (-1, -2, etc.) to create a new session.
    """
    sanitized_name = sanitize_command_name(command)
    
    # Check for existing session
    matching_session = find_matching_session(sanitized_name, "default")
    
    # Handle collision case (only if not force_new)
    if matching_session and not force_new:
        print(f'''<session id="{sanitized_name}">
<error>You already have a session named {matching_session}. Did you mean to use that one? Here are your options:

- If you intended to use it, run `cli-tool get-screen-capture {matching_session}`
- If you want to interrupt it, run `cli-tool kill-session {matching_session}`
- If you really do want a fresh session, run `cli-tool force-run-command "{command}"`
</error>
</session>''')
        return 1
    
    # If force_new and session exists, add a suffix to create a new session
    if matching_session and force_new:
        base_name = sanitized_name
        suffix = 1
        while True:
            test_name = f"{base_name}-{suffix}"
            existing = get_existing_session_ids()
            if test_name not in existing:
                sanitized_name = test_name
                break
            suffix += 1
    
    session_id = sanitized_name
    
    # Create a new tmux session in detached mode
    returncode, stdout, stderr = run_tmux_cmd([
        'new-session', '-d', '-s', session_id
    ])
    
    if returncode != 0:
        print(f'''<session id="{session_id}">
<error>Failed to create session: {stderr}</error>
</session>''')
        return 1
    
    # Send the command to the session
    returncode, stdout, stderr = run_tmux_cmd([
        'send-keys', '-t', session_id, command, 'Enter'
    ])
    
    # Give the command time to start
    time.sleep(1)
    
    # Capture the screen
    screen_capture = capture_pane(session_id)
    
    # Get current program running in the session
    current_program = get_current_program(session_id)
    
    # Build XML output
    print(f'''<session id="{session_id}" current-program="{escape_xml(current_program)}">
<screen-capture>
{screen_capture}
</screen-capture>
</session>
<instructions>
The command has started. To send keystrokes run `cli-tool send-keystrokes` followed by the id and the keystrokes. For instance:

    $ cli-tool send-keystrokes {session_id} "^X"

Run `cli-tool send-keystrokes --help` to find out the full syntax
</instructions>
<random-usage-tip>{get_next_tip()}</random-usage-tip>''')
    
    return 0


def get_screen_capture(session_id: str) -> int:
    """
    Get screen capture for an existing session.
    
    Returns the current screen content without creating a new session.
    """
    # Check if session exists
    returncode, stdout, stderr = run_tmux_cmd(['list-sessions', '-F', '#{session_name}'])
    
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        valid_sessions = [s.strip() for s in stdout.strip().split('\n') if s.strip()]
    
    if session_id not in valid_sessions:
        print(f'''<session id="{session_id}">
<error>Session not found: {session_id}</error>
</session>''')
        return 1
    
    # Capture the screen
    screen_capture = capture_pane(session_id)
    
    # Get current program running in the session
    current_program = get_current_program(session_id)
    
    print(f'''<session id="{session_id}" current-program="{escape_xml(current_program)}">
<screen-capture>
{screen_capture}
</screen-capture>
<random-usage-tip>{get_next_tip()}</random-usage-tip>
</session>''')
    
    return 0


def kill_session(session_id: str) -> int:
    """
    Kill a specific tmux session.
    """
    # Check if session exists
    returncode, stdout, stderr = run_tmux_cmd(['list-sessions', '-F', '#{session_name}'])
    
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        valid_sessions = [s.strip() for s in stdout.strip().split('\n') if s.strip()]
    
    if session_id not in valid_sessions:
        print(f'''<kill-result>
<error>Session not found: {session_id}</error>
</kill-result>''')
        return 1
    
    # Kill the session
    returncode, stdout, stderr = run_tmux_cmd(['kill-session', '-t', session_id])
    
    if returncode == 0:
        print(f'''<kill-result>
<killed sessions="{session_id}" />
<message>Session has been terminated.</message>
</kill-result>''')
    else:
        print(f'''<kill-result>
<error>Failed to kill session: {stderr}</error>
</kill-result>''')
    
    return 0


def send_keystrokes(session_id: str, keystrokes: str, expected_command: Optional[str] = None) -> int:
    """
    Send keystrokes to a tmux session.
    
    Parses special keystrokes like ^X for Ctrl+X, and sends them
    to the specified session.
    
    If expected_command is provided, validates that the current program
    matches. If not, returns an error directing the user to navigate
    from the current program to the expected one.
    """
    # Check if session exists
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', '#{session_name}'
    ])
    
    # Get all sessions
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        valid_sessions = [s.strip() for s in stdout.strip().split('\n') if s.strip()]
    
    if session_id not in valid_sessions:
        print(f'''<session id="{session_id}">
<error>Session not found: {session_id}</error>
</session>''')
        return 1
    
    # Get current program running in the session BEFORE sending keystrokes
    current_program = get_current_program(session_id)
    
    # Validate expected command if provided - check BEFORE sending keystrokes
    if expected_command and current_program.lower() != expected_command.lower():
        # Get a screen capture for context
        screen_capture = capture_pane(session_id)
        
        print(f'''<session id="{session_id}" current-program="{escape_xml(current_program)}">
<error>
The running program is "{escape_xml(current_program)}", not "{escape_xml(expected_command)}".

You need to go from "{escape_xml(current_program)}" to "{escape_xml(expected_command)}".

For example, if you're in a shell, you may need to send the command to start {expected_command}.
If you're in another program, you may need to exit it first (e.g., run `send-keystrokes session-id "exit\n"`, `send-keystrokes session-id "^C"`, or `send-keystrokes session-id ":q"`).
</error>
<screen-capture>
{screen_capture}
</screen-capture>
</session>''')
        return 1
    
    # Parse keystrokes
    keys_to_send = parse_keystrokes(keystrokes)
    
    # Send each key
    for key in keys_to_send:
        returncode, stdout, stderr = run_tmux_cmd([
            'send-keys', '-t', session_id, key
        ])
    
    # Small delay to let the application process
    time.sleep(0.3)
    
    # Capture the screen
    screen_capture = capture_pane(session_id)
    
    # Build XML output
    print(f'''<session id="{session_id}" current-program="{escape_xml(current_program)}">
<keystrokes sent="{escape_xml(keystrokes)}" />
<screen-capture>
{screen_capture}
</screen-capture>
<instructions>
The keystrokes were sent. To send more keystrokes run `cli-tool send-keystrokes` again.
</instructions>
<random-usage-tip>{get_next_tip()}</random-usage-tip>''')
    
    return 0


def parse_keystrokes(keystrokes: str) -> List[str]:
    """
    Parse keystroke string into individual keys.
    
    Handles tmux key syntax:
    - ^X or C-X -> Ctrl+X (Ctrl+key)
    - S-X -> Shift+X
    - M-X -> Alt (meta)+X
    - \n -> Enter
    - \t -> Tab
    - Special keys: Up, Down, Left, Right, BSpace, BTab, DC, End, Escape, F1-F12, Home, etc.
    - Regular characters
    """
    keys = []
    i = 0
    while i < len(keystrokes):
        # Check for modifier prefixes: ^X, C-X, S-X, M-
        if (keystrokes[i] in ('^', 'C', 'S', 'M')) and i + 1 < len(keystrokes):
            # Bounds check for C-X, S-X, M-X formats
            if keystrokes[i] in ('C', 'S', 'M') and keystrokes[i+1] == '-' and i + 2 >= len(keystrokes):
                keys.append(keystrokes[i])
                i += 1
            elif keystrokes[i] == '^' or (keystrokes[i] == 'C' and keystrokes[i+1] == '-'):
                # Ctrl+key (^X or C-X)
                if keystrokes[i] == '^':
                    next_char = keystrokes[i + 1].lower()
                    keys.append(f'C-{next_char}')
                    i += 2
                else:  # C-X format
                    next_char = keystrokes[i + 2].lower()
                    keys.append(f'C-{next_char}')
                    i += 3
            elif keystrokes[i] == 'S' and keystrokes[i+1] == '-':
                # Shift+key
                next_char = keystrokes[i + 2].upper()
                keys.append(f'S-{next_char}')
                i += 3
            elif keystrokes[i] == 'M' and keystrokes[i+1] == '-':
                # Alt (meta)+key
                next_char = keystrokes[i + 2].lower()
                keys.append(f'M-{next_char}')
                i += 3
            else:
                keys.append(keystrokes[i])
                i += 1
        elif keystrokes[i] == '\\':
            # Escape sequence
            if i + 1 < len(keystrokes):
                next_char = keystrokes[i + 1]
                if next_char == 'n':
                    keys.append('Enter')
                elif next_char == 't':
                    keys.append('Tab')
                elif next_char == '\\':
                    keys.append('\\')
                i += 2
            else:
                keys.append(keystrokes[i])
                i += 1
        else:
            keys.append(keystrokes[i])
            i += 1
    
    return keys


def process_info(session_id: str) -> int:
    """
    Get process information for a tmux session.
    
    Returns command line, time since started, and PID in XML format.
    """
    # Get session info
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', '#{session_name}'
    ])
    
    # Get all sessions
    valid_sessions = []
    if returncode == 0 and stdout.strip():
        valid_sessions = [s.strip() for s in stdout.strip().split('\n') if s.strip()]
    
    if session_id not in valid_sessions:
        print(f'''<process-info session-id="{session_id}">
<error>Session not found: {session_id}</error>
</process-info>''')
        return 1
    
    # Get detailed session info including PID
    returncode, stdout, stderr = run_tmux_cmd([
        'display-message', '-t', session_id, '-F', '#{session_created} #{session_name} #{pane_pid}'
    ])
    
    if returncode == 0:
        parts = stdout.strip().split()
        if len(parts) >= 1:
            try:
                created_time = int(parts[0])
                now = int(time.time())
                seconds_running = now - created_time
                
                # Get PID if available (parts[2])
                pid = parts[2] if len(parts) >= 3 else "unknown"
                
                # Format uptime
                if seconds_running < 60:
                    uptime = f"{seconds_running} seconds"
                elif seconds_running < 3600:
                    uptime = f"{seconds_running // 60} minutes"
                else:
                    uptime = f"{seconds_running // 3600} hours"
                
                print(f'''<process-info session-id="{session_id}">
<command>{escape_xml(session_id)}</command>
<uptime>{uptime}</uptime>
<pid>{pid}</pid>
<started-at>{datetime.fromtimestamp(created_time).isoformat()}</started-at>
</process-info>''')
                return 0
            except (ValueError, IndexError):
                pass
    
    print(f'''<process-info session-id="{session_id}">
<command>{escape_xml(session_id)}</command>
<uptime>unknown</uptime>
</process-info>''')
    
    return 0


def kill_all_tools(global_kill: bool = False) -> int:
    """
    Kill all tmux sessions created by cli-tool.
    
    Can be scoped to a specific agent or kill all globally.
    Only kills sessions in the current namespace (unless --global is used).
    """
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', '#{session_name}'
    ])
    
    if returncode != 0:
        print(f'''<kill-result>
<error>Failed to list sessions: {stderr}</error>
</kill-result>''')
        return 1
    
    sessions = stdout.strip().split('\n') if stdout.strip() else []
    killed = []
    
    for session in sessions:
        if session:
            # If global_kill is True, kill everything; otherwise only kill sessions without prefixes
            should_kill = False
            if global_kill:
                should_kill = True
            elif not any(session.startswith(prefix) for prefix in ('cli-', 'tmuxserver-', 'codebuff-')):
                # Kill sessions we created (no prefix)
                should_kill = True
            
            if should_kill:
                run_tmux_cmd(['kill-session', '-t', session])
                killed.append(session)
    
    if killed:
        print(f'''<kill-result>
<killed sessions="{','.join(killed)}" />
<message>All sessions have been terminated.</message>
</kill-result>''')
    else:
        print(f'''<kill-result>
<message>No sessions to kill.</message>
</kill-result>''')
    
    return 0


def list_sessions() -> int:
    """
    List all active tmux sessions.
    
    Returns session ID, current program, and time since last interaction.
    """
    # Get format string: session name, created time, last activity time
    fmt = '#{session_name} #{session_created} #{session_activity}'
    returncode, stdout, stderr = run_tmux_cmd([
        'list-sessions', '-F', fmt
    ])
    
    # If socket doesn't exist (no sessions yet), return empty list
    if returncode != 0 and 'No such file or directory' in stderr:
        print('<sessions/>')
        return 0
    
    if returncode != 0:
        print(f'''<sessions>
<error>Failed to list sessions: {stderr}</error>
</sessions>''')
        return 1
    
    sessions_data = stdout.strip().split('\n') if stdout.strip() else []
    
    # Build XML output with session info
    print('<sessions>')
    for line in sessions_data:
        if not line.strip():
            continue
        parts = line.split(' ', 2)
        if len(parts) >= 3:
            session_name = parts[0]
            created_time = int(parts[1])
            activity_time = int(parts[2])
            
            # Get current program for this session
            current_program = get_current_program(session_name)
            
            # Calculate time since last activity
            current_ts = int(time.time())
            seconds_since_activity = current_ts - activity_time
            
            # Format as human readable
            if seconds_since_activity < 60:
                time_since = f"{seconds_since_activity}s"
            elif seconds_since_activity < 3600:
                time_since = f"{seconds_since_activity // 60}m"
            elif seconds_since_activity < 86400:
                time_since = f"{seconds_since_activity // 3600}h"
            else:
                time_since = f"{seconds_since_activity // 86400}d"
            
            print(f'  <session id="{session_name}" current-program="{escape_xml(current_program)}" last-activity="{time_since}" />')
    print('</sessions>')
    
    return 0


def escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


# Usage tips - cycling through commands starting at process-info
USAGE_TIPS = [
    ("process-info", "diagnose session state (check PID, uptime, if still running)", "cli-tool process-info <session-id>"),
    ("get-screen-capture", "see the current screen without sending keystrokes", "cli-tool get-screen-capture <session-id>"),
    ("send-keystrokes", "send keystrokes to control the program", "cli-tool send-keystrokes <session-id> 'keys'"),
    ("list-sessions", "see all active sessions", "cli-tool list-sessions"),
    ("kill-session", "terminate a specific session", "cli-tool kill-session <session-id>"),
    ("kill-all-tools", "terminate all sessions in your namespace", "cli-tool kill-all-tools"),
]


def get_next_tip() -> str:
    """
    Get the next usage tip, cycling through commands.
    
    Starts at process-info and cycles through all commands.
    """
    global _last_tip_index
    _last_tip_index = (_last_tip_index + 1) % len(USAGE_TIPS)
    cmd, description, example = USAGE_TIPS[_last_tip_index]
    return f"If you need to {description}, use {example}"


def main():
    """Main entry point for agent-cli-helper."""
    parser = argparse.ArgumentParser(
        description='A tool for LLMs and agents to interface interactive applications from the CLI.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # new-command
    new_cmd_parser = subparsers.add_parser(
        'run-command',
        help='Run a program in a session'
    )
    new_cmd_parser.add_argument(
        'cmd',
        help='The command to run (e.g., "nano some-file")'
    )
    
    # force-run-command
    force_cmd_parser = subparsers.add_parser(
        'force-run-command',
        help='Force run a program (bypass collision check)'
    )
    force_cmd_parser.add_argument(
        'cmd',
        help='The command to run (e.g., "nano some-file")'
    )
    
    # get-screen-capture
    capture_parser = subparsers.add_parser(
        'get-screen-capture',
        help='Get screen capture for an existing session'
    )
    capture_parser.add_argument(
        'session_id',
        help='The session ID to get screen capture for'
    )
    
    # kill-session
    kill_sess_parser = subparsers.add_parser(
        'kill-session',
        help='Kill a specific session'
    )
    kill_sess_parser.add_argument(
        'session_id',
        help='The session ID to kill'
    )
    
    # send-keystrokes
    send_parser = subparsers.add_parser(
        'send-keystrokes',
        help='Send keystrokes to a session'
    )
    send_parser.add_argument(
        'session_id',
        help='The session ID to send keystrokes to'
    )
    send_parser.add_argument(
        '--expected-command', '-e',
        metavar='CMD',
        help='Expected program running in session (e.g., vim, ssh, nano). If the actual program differs, returns an error.'
    )
    send_parser.add_argument(
        'keystrokes',
        help='Keystrokes to send. Use ^X or C-X for Ctrl+X, S-X for Shift+X, M-X for Alt (meta)+X, ' +
             '\\n for Enter, \\t for Tab. Special keys: Up, Down, Left, Right, BSpace, BTab, DC (Delete), ' +
             'End, Escape, F1-F12, Home, IC, NPage/PgDn, PPage/PgUp, Space, Tab'
    )
    
    # process-info
    proc_parser = subparsers.add_parser(
        'process-info',
        help='Get process information for a session'
    )
    proc_parser.add_argument(
        'session_id',
        help='The session ID to get info for'
    )
    
    # kill-all-tools
    kill_parser = subparsers.add_parser(
        'kill-all-tools',
        help='Kill all cli-tool sessions'
    )
    
    # list (for --global)
    list_parser = subparsers.add_parser(
        'list-sessions',
        help='List all sessions'
    )
    
    args = parser.parse_args()
    
    # If no command is provided, print help and exit with 1
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Dispatch to appropriate command handler
    if args.command == 'run-command':
        return new_command(args.cmd, force_new=False)
    elif args.command == 'force-run-command':
        return new_command(args.cmd, force_new=True)
    elif args.command == 'get-screen-capture':
        return get_screen_capture(args.session_id)
    elif args.command == 'kill-session':
        return kill_session(args.session_id)
    elif args.command == 'send-keystrokes':
        return send_keystrokes(args.session_id, args.keystrokes, expected_command=args.expected_command)
    elif args.command == 'process-info':
        return process_info(args.session_id)
    elif args.command == 'kill-all-tools':
        return kill_all_tools(global_kill=False)
    elif args.command == 'list-sessions':
        return list_sessions()
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
