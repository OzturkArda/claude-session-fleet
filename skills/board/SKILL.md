---
name: board
description: Shows the session fleet - every live session's context against the cap, the manager, retiring sessions, handovers no successor has picked up, and recent ledger events. Use when the user asks for the board, the fleet, "who is running" or "how much context do my sessions have left".
---

# Board

## Required output

In this order, and nothing more:

1. **Needs attention**: sessions marked `HANDOVER DUE` (at the cap with no handover yet: give them no
   new work), and handovers whose successor is `NOT FOUND`, `STOPPED` or `FAILED` or that show
   `NO SUCCESSOR STARTED`. A `DONE` successor finished its work and needs nothing.
2. **Headroom**: sessions above 80% of the cap.
3. **Roster**: one line per live session: ticket, name, short id, context, role.

## Steps

1. When no live session holds the manager role, take it. `--declare-if-vacant` leaves the role with
   a live holder, so opening the board from a developer session never moves it:

   ```
   session-fleet manager --declare-if-vacant --session ${CLAUDE_SESSION_ID} --name "<this session's name>"
   ```

   Report its one-line output with the board.

2. Run `session-fleet board [--ticket $ARGUMENTS]` and report as above.

Run the script again on every request rather than carrying the roster forward in this session's
context: the board is rebuilt from disk each time, which keeps a manager's context flat and lets a
fresh session take over the role at any point.

To reach a session, find its exact name with `ListAgents` and use `SendMessage`.
