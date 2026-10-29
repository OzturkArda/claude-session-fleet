---
name: start-fleet
description: Makes this session the manager and starts one background developer session per ticket, each optionally in its own git worktree. Use when the user says "start a fleet", "start sessions for PROJ-1 PROJ-2 PROJ-3" or "I'll manage these tickets from here".
disable-model-invocation: true
---

# Start a fleet

## Required output

One line per started session, then a pointer to the board:

```
PROJ-1  ·  PROJ-1 dev  ·  3f9c1a2b  ·  C:\repos\app\.claude\worktrees\PROJ-1  ·  claude attach 3f9c1a2b
```

**Arguments (`$ARGUMENTS`):** ticket keys separated by spaces, plus `--repo <path>` for a worktree per
ticket or `--cwd <path>` for one shared directory.

## Steps

1. **Claim the manager role**, so sessions that retire or escalate have somewhere to report:

   ```
   session-fleet manager --declare --session ${CLAUDE_SESSION_ID} --name "<this session's name>"
   ```

2. **Decide where each session runs.**
   - `--repo <path>`: each ticket gets `<repo>/.claude/worktrees/<TICKET>` on branch `issue/<TICKET>`.
   - `--cwd <path>`: all sessions start there. Sessions sharing one checkout fight over the branch,
     so this suits work that is not on branches.
   - Neither: ask once for all tickets together.

3. **Start one session per ticket:**

   ```
   session-fleet launch --ticket <KEY> [--repo <path> --worktree | --cwd <path>] ["<prompt>"]
   ```

   Pass a prompt only when the user gave instructions for that ticket. Without one, the default
   briefing tells the session to read its ticket itself. Leave the tickets unread here: a manager
   that reads five tickets to brief five sessions fills its own context with work the developer
   sessions do anyway, and a manager's context has to last the whole fleet. Keep the context cap and
   handovers out of every prompt, because a session that knows it is on a budget rations itself
   from the first turn.

4. **Report** one line per session as above, then say that `/session-fleet:board` shows the
   fleet. If a launch failed, name the ticket and the reason, and leave the others running.
