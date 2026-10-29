---
name: join-fleet
description: Puts this session under the fleet's manager - records it as a member and tells the manager what it is working on. Use when the user says "join the fleet", "report to the manager" or "assign yourself to the manager".
---

# Join the fleet

1. Run:

   ```
   session-fleet join --session ${CLAUDE_SESSION_ID} --name "<this session's name>"
   ```

2. When it prints a manager name, send that session one line with `SendMessage`: this session's
   name, short id, ticket or topic, and working directory. From then on, report blockers and
   decisions that need the user to the manager the same way, and the board lists this session as a
   member.

3. When it prints `no live manager`, say so in one line and carry on as a standalone session. A fleet
   without a manager is a normal state; the user starts one with `/session-fleet:start-fleet`
   or by opening `/session-fleet:board`.
