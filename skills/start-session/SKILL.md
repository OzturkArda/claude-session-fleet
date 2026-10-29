---
name: start-session
description: Starts one background Claude Code session on a prompt the user wrote, passed through verbatim, and reports its name and id for `claude attach`. Use when the user says "start a session", "spin up a session for PROJ-1234" or "launch a background session to ...".
disable-model-invocation: true
---

# Start a session

## Required output

```
<name>  ·  <short id>  ·  <cwd>
attach: claude attach <short id>
```

## Steps

1. Run, with the user's prompt from `$ARGUMENTS` passed through **verbatim**:

   ```
   session-fleet launch [--cwd <path>] [--name "<name>"] "<the prompt>"
   ```

   The new session reads its own ticket, so the prompt goes as written: a summary or an added
   briefing would replace the user's instructions with this session's reading of them.

   - The name comes from the first ticket key in the prompt (`PROJ-1` gives `PROJ-1 dev`), with ` #2`,
     ` #3` added when a live session already answers to it.
   - `--cwd` defaults to this session's directory. When the work would collide with another
     session's checkout, start it in its own directory, or use `--repo <path> --worktree` for a
     ticket worktree.
   - When a live manager exists, the script appends its name to the prompt, so an instruction to
     escalate has an address. `--no-manager-note` leaves the prompt untouched.

2. Report the name, short id, directory and attach command printed by the script, then stop. The new
   session works on its own from here; `/session-fleet:board` shows it.

The context cap and handovers stay out of every prompt: a session that knows it is on a budget
rations itself from the first turn, and the cap's Stop hook handles the moment itself.

If the launch fails because the directory is not trusted, tell the user to run `claude` once in that
directory and accept the trust prompt.
