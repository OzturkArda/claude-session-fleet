# Session fleet

Sessions that start and manage other sessions. One session holds the manager role and starts
background sessions per ticket or per prompt; other sessions can join it; a session that hands over
at the context cap starts its own successor and tells the manager; the board shows the whole fleet.

Packaged as a Claude Code plugin, `session-fleet`. It builds on
[`session-cap`](https://github.com/OzturkArda/claude-session-cap), which installs with it as a dependency: the fleet
shares that plugin's ledger, context counting and handover document.

## How it fits together

```
manager session ──start-fleet / start-session──▶ background sessions (claude --bg)
      ▲                                                │
      │ SendMessage: joined, blocked, retiring         │ context cap trips (session-cap)
      │                                                ▼
      └──────────────────────────────── handover ──▶ successor started, linked by session id
```

- **Manager role.** A `manager` event in the ledger names the session holding it; the claim lasts
  while that session is live. A fleet without a manager is a normal state, and every step that
  would notify one skips quietly.
- **Ledger.** `~/.claude/session-cap/ledger.jsonl` records `spawn`, `join`, `manager`, `at-cap` and
  `handover` events. Sessions are linked by session id, never by name, so renaming a session breaks
  nothing.
- **Liveness.** A session is live while `claude agents --json` lists it in a state other than
  `done`, `stopped` or `failed`.
- **Managers stay light.** Developer sessions read their own tickets, and the board is rebuilt from
  disk on every call, so a manager's context lasts the whole fleet and a fresh session can take the
  role over at any point.

## What it adds

| Part | Trigger | Effect |
|---|---|---|
| `/session-fleet:start-fleet <KEY>...` | the user | Declares this session manager, then starts one background session per ticket, in a worktree per ticket with `--repo <path>` |
| `/session-fleet:start-session <prompt>` | the user | Starts one background session on the prompt, verbatim; appends the manager's name when one is live |
| `/session-fleet:join-fleet` | the user | Records this session as a member and reports to the manager |
| `/session-fleet:board` | the user | Live sessions with context against the cap, role and state; handovers whose successor is missing; recent ledger events. Takes the manager role when it is vacant |
| `session-cap:handover` steps 4 and 6 | the cap trip | With this plugin installed, the handover starts the successor itself and messages the manager |
| `session_fleet.py pickup` | `SessionStart` hook | A session that is a recorded successor is pointed at its handover document, including after `/clear` or a resume |
| `session-fleet` | Bash tool | The command behind the skills, on the Bash tool's `PATH` while the plugin is enabled. `session-fleet --help` lists its subcommands |

Worktrees go to `<repo>/.claude/worktrees/<TICKET>` on branch `issue/<TICKET>`. The launcher checks
that git registers the path as a worktree, and refuses a directory that merely exists there, because
such a directory resolves to the parent checkout and its branch.

## Install

Needs everything [`session-cap`](https://github.com/OzturkArda/claude-session-cap#install) needs, plus a Claude Code
version with background sessions (`claude --bg`, `claude agents --json`, `claude attach`) and the
`SendMessage` and `ListAgents` tools.

```
/plugin marketplace add OzturkArda/claude-session-fleet
/plugin install session-fleet@session-fleet
```

The marketplace lists `session-cap` too, fetched from its own repository, so the dependency
installs with the fleet.

Start one new session after installing: `session-cap` copies the shared script into
`~/.claude/session-cap/` at session start, and the fleet commands read it from there.

Background sessions start only in a directory Claude Code trusts. When a launch fails on trust, run
`claude` once in that directory and accept the prompt.

To turn the fleet off and keep the cap: `/plugin disable session-fleet`.

## Repository layout

```
.claude-plugin/plugin.json        plugin manifest, depends on session-cap
.claude-plugin/marketplace.json   marketplace listing this plugin and session-cap
bin/session-fleet                 wrapper put on the Bash tool's PATH
hooks/hooks.json                  SessionStart hook (pickup)
scripts/session_fleet.py          launch, manager, join, board, pickup
skills/                           start-fleet, start-session, join-fleet, board, each with evals
```

## License

[MIT](LICENSE)
