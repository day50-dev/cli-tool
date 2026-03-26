---
name: agent-cli-helper-skill
description: Run interactive CLI programs in isolated tmux sessions, send keystrokes, capture screen output. Use for vim, nano, ssh, emacs, ipdb, and any terminal-based interactive applications. Keywords: terminal, interactive, tmux, shell, vim, ssh, emacs, debugger.
compatibility: Requires tmux installed on system
---

# agent-cli-helper Skill

Use this skill when you need to interact with full-screen terminal applications like:
- Text editors: vim, nano, emacs
- Remote connections: ssh, telnet
- Debuggers: pdb, ipdb, gdb
- Any interactive CLI program

## Quick Reference

| Command | Purpose |
|---------|---------|
| `agent-cli-helper run-command "<cmd>"` | Start a program in a session |
| `agent-cli-helper send-keystrokes <session-id> "<keys>"` | Send keystrokes to session |
| `agent-cli-helper get-screen-capture <session-id>` | Get current screen |
| `agent-cli-helper process-info <session-id>` | Get PID, uptime |
| `agent-cli-helper kill-session <session-id>` | Kill a session |
| `agent-cli-helper list-sessions` | List all sessions |

## Session ID Format

Session IDs are derived from the command. Examples:
- `ssh fanon.local` → `ssh-fanon-local`
- `vim /tmp/file.txt` → `vim-tmp-file`
- `python -m ipdb script.py` → `python-m-ipdb`

## Keystroke Syntax

- `^X` or `C-X` → Ctrl+X
- `\n` → Enter
- `\t` → Tab
- `Up`, `Down`, `Left`, `Right` → Arrow keys
- `BSpace` → Backspace
- `F1`-`F12` → Function keys

## Session Isolation

Each agent instance gets its own tmux socket namespace (via `-L` flag). Sessions are isolated between different agent instances.

## Error Handling

If a session already exists with the same name, you'll get a collision error. Use `agent-cli-helper force-run-command` to create a new session anyway.

## Important Notes

- Always check the `<screen-capture>` in the output to see program state
- Use `process-info` to check if a session is still alive
- Sessions persist until explicitly killed - don't forget to clean up