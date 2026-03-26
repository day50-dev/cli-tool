# cli-tool - LLMs and Agents Documentation

> **IMPORTANT**: This file is for LLMs and agents only. See `humans.md` for human-facing documentation.

cli-tool is a wrapper around tmux that gives LLMs an easier way to interact with full-screen terminal applications.

## When to Use cli-tool

Use cli-tool when you need to:
- Edit files with vim, nano, or emacs
- SSH into remote servers
- Use interactive debuggers (pdb, ipdb, gdb)
- Run any terminal-based interactive program
- Test CLI applications that require user input

## Available Commands

### run-command
Start a program in an interactive session:
```
cli-tool run-command "vim /tmp/file.txt"
cli-tool run-command "ssh user@host"
cli-tool run-command "python -m ipdb script.py"
```

Returns XML with session ID and screen capture.

### send-keystrokes
Send keystrokes to a running session:
```
cli-tool send-keystrokes vim-tmp-file "iHello World\nEscape"
cli-tool send-keystrokes ssh-user-host "^C"
```

Keystroke syntax:
- `^X` or `C-X` = Ctrl+X
- `\n` = Enter
- `\t` = Tab
- `Up`, `Down`, `Left`, `Right` = Arrow keys
- `BSpace` = Backspace

### get-screen-capture
Get current screen content without sending keystrokes:
```
cli-tool get-screen-capture vim-tmp-file
```

### process-info
Get session details (PID, uptime):
```
cli-tool process-info vim-tmp-file
```

### kill-session
Terminate a specific session:
```
cli-tool kill-session vim-tmp-file
```

### list-sessions
List all active sessions in your namespace:
```
cli-tool list-sessions
```

### force-run-command
Create a new session even if one with the same name exists:
```
cli-tool force-run-command "vim /tmp/file.txt"
```

## Session ID Generation

Session IDs are automatically generated from the command:
- `vim /tmp/test.py` → `vim-tmp-test`
- `ssh fanon.local` → `ssh-fanon-local`
- `python script.py` → `python-script`

## Session Isolation

Each agent instance gets its own tmux socket namespace (format: `cltl-PID_procname`). You can only see and interact with sessions created by your agent instance.

## Error Recovery

If a session already exists:
1. Use the existing session with `get-screen-capture`
2. Kill it first with `kill-session`
3. Use `force-run-command` to create a new one anyway

## Important Notes

- Always check `<screen-capture>` in output to see program state
- Sessions persist until explicitly killed
- Use `process-info` to check if a session is still alive
- The output is "fake XML" - screen capture is raw terminal output, not escaped