"""Session fleet: start sessions, hold the manager role, and show the fleet.

Built on session-cap: it shares that plugin's ledger and reads context the
same way, by importing the copy of session_cap.py that plugin keeps at
~/.claude/session-cap/.

    session_fleet.py launch    start one background session, optionally in a ticket worktree
    session_fleet.py manager   resolve, declare or clear the manager session
    session_fleet.py join      record this session as a member of the manager's fleet
    session_fleet.py board     live sessions, context, retiring sessions, unclaimed handovers
    session_fleet.py pickup    SessionStart hook: points a successor at its handover

A session is live while `claude agents --json` lists it in a state other than
done, stopped or failed.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

CAP_LIB = os.path.join(os.path.expanduser("~"), ".claude", "session-cap")
sys.path.insert(0, CAP_LIB)
try:
    import session_cap as cap
except ImportError:
    cap = None

ENDED = {"done", "stopped", "failed"}
UUID_RE = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
SHORT_ID_RE = re.compile(r"\b[0-9a-f]{8}\b")
TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


def need_cap():
    if cap is None:
        sys.exit("session-cap is not set up: install it, then start one new session so it "
                 "copies session_cap.py to %s" % CAP_LIB)


def claude_bin():
    exe = shutil.which("claude")
    if not exe:
        sys.exit("the `claude` CLI is not on PATH")
    return exe


def all_sessions():
    """Every session `claude agents` knows, including finished background ones."""
    exe = shutil.which("claude")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "agents", "--json", "--all"], capture_output=True, timeout=30)
        rows = json.loads(out.stdout.decode("utf-8", errors="replace") or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("sessionId")]


def live_sessions(rows=None):
    """Sessions still running: interactive ones, and background ones not done, stopped or failed."""
    return [r for r in (all_sessions() if rows is None else rows) if r.get("state") not in ENDED]


def find_live(live, session_id):
    for s in live:
        if s["sessionId"] == session_id:
            return s
    return None


def unique_name(name, live):
    # Names are how sessions address each other (SendMessage, claude attach),
    # so a name a live session already answers to gets a numeric suffix.
    taken = {s.get("name") for s in live}
    if name not in taken:
        return name
    base = re.sub(r" #\d+$", "", name)
    for n in range(2, 100):
        candidate = "%s #%d" % (base, n)
        if candidate not in taken:
            return candidate
    sys.exit("no free name based on %r" % name)


# --- manager -----------------------------------------------------------------

def resolve_manager(live=None):
    """The live holder of the manager role, or None. A claim lasts while its session runs."""
    claims = cap.events(event="manager")
    if not claims:
        return None
    last = claims[-1]
    if last.get("note") == "cleared" or not last.get("session"):
        return None
    hit = find_live(live if live is not None else live_sessions(), last["session"])
    if not hit:
        return None
    return {"session": last["session"], "name": hit.get("name") or last.get("name")}


def cmd_manager(args):
    need_cap()
    if args.declare or args.declare_if_vacant:
        if not args.session:
            sys.exit("--session is required to declare")
        held = resolve_manager()
        if args.declare_if_vacant and held and held["session"] != args.session:
            print("manager: %s (%s) - role left with that session" % (held["name"], held["session"][:8]))
            return 0
        if not (held and held["session"] == args.session):
            cap.add_event("manager", session=args.session, name=args.name)
        print("manager: %s (this session)" % (args.name or args.session[:8]))
        return 0
    if args.clear:
        cap.add_event("manager", note="cleared")
        print("manager role cleared")
        return 0
    held = resolve_manager()
    if not held:
        return 1  # no manager is a normal state, not a fault
    print(held["name"])
    return 0


def cmd_join(args):
    need_cap()
    held = resolve_manager()
    if not held:
        print("no live manager - nothing to join")
        return 1
    cap.add_event("join", session=args.session, name=args.name, manager=held["session"])
    print("joined: %s - send it one line with SendMessage to \"%s\"" % (held["name"], held["name"]))
    return 0


# --- launch ------------------------------------------------------------------

def norm(path):
    return os.path.normcase(os.path.abspath(path)).rstrip("\\/")


def ensure_worktree(repo, ticket, dry_run):
    """<repo>/.claude/worktrees/<TICKET> on issue/<TICKET>, created when absent.

    Whether git registers the path is what counts, not whether a directory sits
    there: an unregistered directory resolves to the parent checkout, so the
    session would look isolated while committing to whatever that has out.
    """
    if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(os.path.join(repo, ".git")):
        sys.exit("not a git repository: %s" % repo)
    wt = os.path.join(repo, ".claude", "worktrees", ticket)
    branch = "issue/" + ticket
    subprocess.run(["git", "-C", repo, "worktree", "prune"], capture_output=True)
    listed = subprocess.run(["git", "-C", repo, "worktree", "list", "--porcelain"], capture_output=True)
    registered = {norm(l[9:]) for l in listed.stdout.decode("utf-8", errors="replace").splitlines()
                  if l.startswith("worktree ")}
    if norm(wt) in registered:
        return wt
    if os.path.exists(wt):
        sys.exit("%s exists but git does not register it as a worktree of %s - remove it first" % (wt, repo))
    if dry_run:
        return wt + "  (would create on %s)" % branch
    has_branch = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", branch],
                                capture_output=True).returncode == 0
    argv = ["git", "-C", repo, "worktree", "add"] + ([wt, branch] if has_branch else ["-b", branch, wt])
    made = subprocess.run(argv, capture_output=True)
    if made.returncode != 0 or not os.path.isdir(wt):
        sys.exit("could not create worktree at %s: %s" % (wt, made.stderr.decode("utf-8", errors="replace").strip()))
    return wt


DEFAULT_BRIEF = """You are the developer session for {ticket}, working in {cwd}.

Read the ticket and its comments yourself, with whichever issue tracker tool this session
has. Report what you find before making changes."""


def cmd_launch(args):
    need_cap()
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
    else:
        prompt = args.prompt
    ticket = args.ticket.upper() if args.ticket else None
    if not ticket and prompt:
        m = TICKET_RE.search(prompt)
        ticket = m.group(0) if m else None

    if args.worktree:
        if not (args.repo and ticket):
            sys.exit("--worktree needs --repo and a ticket")
        cwd = ensure_worktree(os.path.abspath(args.repo), ticket, args.dry_run)
    else:
        cwd = os.path.abspath(args.cwd or os.getcwd())
        if not os.path.isdir(cwd):
            sys.exit("no such directory: %s" % cwd)

    if not prompt:
        if not ticket:
            sys.exit("give a prompt, or a ticket for the default briefing")
        prompt = DEFAULT_BRIEF.format(ticket=ticket, cwd=cwd)

    live = live_sessions()
    name = unique_name(args.name or ("%s dev" % ticket if ticket else "session"), live)

    # A prompt that tells the session to escalate needs an address to escalate to.
    manager = None if args.no_manager_note else resolve_manager(live)
    if manager:
        prompt += ('\n\n---\nThis fleet\'s manager session is named "%s". To reach it, use '
                   "SendMessage addressed to that name." % manager["name"])

    if args.dry_run:
        print(json.dumps({"name": name, "ticket": ticket, "cwd": cwd, "prompt": prompt}, indent=2))
        return 0

    out = subprocess.run([claude_bin(), "--bg", "-n", name, prompt], cwd=cwd, capture_output=True, timeout=120)
    text = (out.stdout + out.stderr).decode("utf-8", errors="replace").strip()
    m = UUID_RE.search(text) or SHORT_ID_RE.search(text)
    if out.returncode != 0 or not m:
        sys.exit("launch failed: %s" % (text or "exit %d" % out.returncode))
    short = m.group(0)[:8]

    # --bg prints the short id that `claude attach` takes; the ledger keys on the
    # full session id, so resolve it while the session registers.
    session = None
    for _ in range(10):
        hit = [s for s in live_sessions() if s["sessionId"].startswith(short)]
        if hit:
            session = hit[0]["sessionId"]
            break
        time.sleep(0.5)

    cap.add_event("spawn", session=session or short, id=short, name=name, ticket=ticket, cwd=cwd,
                  manager=manager["session"] if manager else None, note=args.note)
    print(json.dumps({"name": name, "id": short, "session": session, "ticket": ticket, "cwd": cwd,
                      "attach": "claude attach %s" % short}, indent=2))
    return 0


# --- board -------------------------------------------------------------------

def transcript_map():
    """One walk of ~/.claude/projects for the whole board, newest file per session id."""
    found = {}
    for root, _dirs, files in os.walk(cap.PROJECTS):
        if os.path.basename(root) == "subagents":
            continue
        for f in files:
            if f.endswith(".jsonl"):
                p = os.path.join(root, f)
                sid = f[:-6]
                if sid not in found or os.path.getmtime(p) > os.path.getmtime(found[sid]):
                    found[sid] = p
    return found


def cmd_board(args):
    need_cap()
    limit = cap.get_cap()
    everyone = all_sessions()
    live = live_sessions(everyone)
    manager = resolve_manager(live)
    transcripts = transcript_map()
    members = {e.get("session") for e in cap.events(event="spawn") + cap.events(event="join")}
    handovers = cap.events(event="handover")
    handed = {h.get("session"): h for h in handovers}

    print("=== SESSIONS (cap {:,}) ===".format(limit))
    rows = []
    for s in live:
        usage = cap.context_used(transcripts.get(s["sessionId"]))
        rows.append((usage["used"] if usage else -1, s))
    rows.sort(key=lambda r: r[0], reverse=True)
    if args.ticket:
        rows = [r for r in rows if cap.ticket_for(r[1].get("cwd"), r[1].get("name")) == args.ticket]
    for used, s in rows:
        sid = s["sessionId"]
        if used < 0:
            ctx, pct = "    ?", "   ?"
        else:
            ratio = used / float(limit) if limit > 0 else 0
            ctx = "%4dk" % round(used / 1000.0)
            # Past the cap a fill percentage stops reading as a fill, so say how far past.
            pct = "%.1fx" % ratio if limit > 0 and used >= limit else "%3d%%" % round(100 * ratio)
        role = "manager" if manager and manager["session"] == sid else "member" if sid in members else ""
        flag = "handed over" if sid in handed else "HANDOVER DUE" if os.path.exists(
            os.path.join(cap.TRIPPED, sid)) else ""
        print("%s %5s  %-8s %-8s %-12s %-10s %s" % (ctx, pct, sid[:8], s.get("state") or "", flag, role,
                                                   s.get("name") or ""))
    if not rows:
        print("no live sessions")
    print()

    print("=== MANAGER ===")
    print("%s (%s)" % (manager["name"], manager["session"][:8]) if manager else "none")
    print()

    print("=== HANDOVERS IN THE LAST 48H ===")
    cutoff = datetime.datetime.now().astimezone() - datetime.timedelta(hours=48)
    shown = 0
    for h in handovers:
        try:
            ts = datetime.datetime.fromisoformat(h.get("ts"))
        except (TypeError, ValueError):
            continue
        if ts < cutoff or (args.ticket and h.get("ticket") != args.ticket):
            continue
        succ = h.get("successorSession")
        if succ:
            known = find_live(everyone, succ)
            if not known:
                state = "successor NOT FOUND"
            elif known.get("state") in ENDED:
                state = "successor %s" % known["state"].upper()
            else:
                state = "successor live"
        else:
            state = "NO SUCCESSOR STARTED"
        print("%s  %-8s -> %-22s %-22s %s" % (h["ts"][:16], (h.get("session") or "")[:8],
                                              h.get("successor") or "-", state, h.get("file")))
        shown += 1
    if not shown:
        print("none")
    print()

    print("=== LEDGER (last %d) ===" % args.events)
    rows = cap.events(ticket=args.ticket)[-args.events:]
    for e in rows:
        extra = " | ".join(str(e[k]) for k in ("name", "successor", "file", "note") if e.get(k))
        print("%s  %-8s %-9s %-8s %s" % (e.get("ts", "")[:16], (e.get("session") or "")[:8], e.get("event"),
                                         e.get("ticket") or "", extra))
    if not rows:
        print("empty")
    return 0


# --- hook --------------------------------------------------------------------

def shell_path(path):
    """A directory as a PATH entry for the Bash tool's shell; on Windows that is Git Bash."""
    path = path.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", path)
    if os.name == "nt" and m:
        return "/%s/%s" % (m.group(1).lower(), m.group(2))
    return path


def export_bin():
    """Put the plugin's bin/ on the Bash tool's PATH for this session.

    A SessionStart hook's CLAUDE_ENV_FILE is sourced before every Bash command,
    so `session-fleet` resolves from any skill, including the handover skill of
    session-cap, and only while this plugin is enabled. The export is
    skipped when bin/ is already on PATH, as it is when Claude Code adds a
    plugin's bin/ itself.
    """
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    bindir = shell_path(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))
    with open(env_file, "a", encoding="utf-8", newline="\n") as fh:
        fh.write('case ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n' % (bindir, bindir))


def cmd_pickup(_args):
    """SessionStart hook. Exports the command, and points a successor at its handover.

    The successor is matched by session id, recorded when the handover started
    it, so a rename cannot break the link. The note carries a pointer only, so
    sessions that are not successors pay nothing.
    """
    try:
        export_bin()
    except OSError:
        pass
    if cap is None or cap.get_cap() <= 0:
        return
    data = cap.read_hook_input()
    sid = (data or {}).get("session_id")
    if not sid:
        return
    mine = [h for h in cap.events(event="handover") if h.get("successorSession") == sid]
    if not mine or not mine[-1].get("file") or not os.path.isfile(mine[-1]["file"]):
        return
    h = mine[-1]
    lines = ["This session is the recorded successor of session %s." % (h.get("session") or "?")[:8],
             "  handover document: %s" % h["file"],
             "Read that document before anything else."]
    manager = resolve_manager()
    if manager:
        lines.append('Then tell the manager session "%s" with SendMessage that you have picked it up.'
                     % manager["name"])
    cap.emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}})


def main(argv=None):
    p = argparse.ArgumentParser(prog="session-fleet", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    la = sub.add_parser("launch", help="start one background session")
    la.add_argument("prompt", nargs="?", help="the prompt, passed through verbatim")
    la.add_argument("--prompt-file")
    la.add_argument("--name")
    la.add_argument("--ticket")
    la.add_argument("--cwd")
    la.add_argument("--repo", help="with --worktree: the repository to add the ticket worktree to")
    la.add_argument("--worktree", action="store_true")
    la.add_argument("--no-manager-note", action="store_true")
    la.add_argument("--note")
    la.add_argument("--dry-run", action="store_true")
    la.set_defaults(fn=cmd_launch)

    ma = sub.add_parser("manager", help="resolve, declare or clear the manager")
    grp = ma.add_mutually_exclusive_group()
    grp.add_argument("--declare", action="store_true")
    grp.add_argument("--declare-if-vacant", action="store_true")
    grp.add_argument("--clear", action="store_true")
    ma.add_argument("--session")
    ma.add_argument("--name")
    ma.set_defaults(fn=cmd_manager)

    jo = sub.add_parser("join", help="join the live manager's fleet")
    jo.add_argument("--session", required=True)
    jo.add_argument("--name")
    jo.set_defaults(fn=cmd_join)

    bo = sub.add_parser("board", help="the fleet at a glance")
    bo.add_argument("--ticket")
    bo.add_argument("--events", type=int, default=20)
    bo.set_defaults(fn=cmd_board)

    sub.add_parser("pickup").set_defaults(fn=cmd_pickup)

    args = p.parse_args(argv)
    if args.cmd == "pickup":
        try:
            args.fn(args)
        except Exception:
            pass
        return 0
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
