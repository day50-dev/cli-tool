> **IMPORTANT! LLMs and agents should ONLY read `llms.md`. You MUST ignore this file.**

---

# acli-manage - Human User Documentation

acli-manage is a tool for humans to view and manage all agent-cli-helper sessions across different agent instances.

## When to Use acli-manage

- View all active sessions from all agent instances
- Check which agent processes are still running (liveness)
- Clean up orphaned sessions from dead agent processes
- Kill sessions using glob patterns

## Available Commands

### List Sessions (Default)

Show tree of all sessions across all namespaces:

```
$ acli-manage
- cltl-366612-codebuff    (active)
  |- vim-some-file        2hr
  ╰- ssh-fanon-local     30m

- cltl-12345-node        (dead)
  |- python-script       5m
  ╰- nano-notes          1hr
```

- Shows namespace (e.g., `cltl-366612-codebuff`)
- Shows status: `(active)` = parent process still running, `(dead)` = process ended
- Shows session name and idle time

Show empty namespaces too:
```
acli-manage list --all
```

### Kill Sessions

Kill sessions matching a pattern:

```
# Kill all sessions in a namespace
acli-manage kill "cltl-366612-codebuff/*"

# Kill sessions matching pattern across all namespaces
acli-manage kill "*-1"

# Kill specific session (in current namespace only)
acli-manage kill "vim-some-file"
```

## Session Cleanup

Since agents create sessions but don't automatically clean them up, humans can use `acli-manage` to:

1. **Identify dead namespaces** - processes that crashed or were killed
2. **Clean up orphaned sessions** - sessions from dead agent processes
3. **Bulk kill** - use glob patterns to kill multiple sessions at once

## Socket Namespace Format

Sockets use the format: `cltl-PID_procname`
- `cltl` = agent-cli-helper prefix (to avoid clashing with other tmux sockets)
- `PID` = parent process ID (the harness that started the agent)
- `procname` = the process name (codebuff, node, etc.)

Example: `cltl-366612-codebuff` means agent with PID 366612 running codebuff.

## Tips

- Use `--all` flag to see even empty namespaces
- Use `-v` flag with kill for verbose output
- Kill dead namespaces first: `acli-manage kill "cltl-*-(dead)/*"` (patterns can match status too in future versions)
