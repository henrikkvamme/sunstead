#!/usr/bin/env bash
# Move the current Claude Code session to the devme remote host:
#   1. sync the working tree (devme remote sync / mutagen)
#   2. copy the session transcript (+ project memory) into the remote
#      ~/.claude/projects/<slug>/ matching the remote project path
#   3. seed a "claude" tab in the project's herdr session on the host,
#      running `claude --resume <session-id>` in the project dir
# so that `devme remote` (herdr attach preset) lands straight in the
# resumed session.
#
# Usage: move-session.sh [session-id]
#   Run from the project root (the directory the Claude session was
#   started in). Without an argument, the most recently active session
#   for this directory is moved.
set -euo pipefail

say() { printf '%s\n' "$*" >&2; }
die() { say "devme remote-session: error: $*"; exit 1; }

# Scan ssh/herdr output for the first JSON line and print the value at the
# given dotted path ('' when absent). herdr CLIs print one JSON object.
jpath() {
    python3 -c '
import sys, json

def first_json(text):
    # Pretty-printed output (devme remote status --json): parse from the
    # first brace to the end. Single-line-JSON-amid-noise (herdr CLIs):
    # fall back to a per-line scan.
    i = text.find("{")
    if i != -1:
        try:
            return json.loads(text[i:])
        except json.JSONDecodeError:
            pass
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None

path = sys.argv[1].split(".")
d = first_json(sys.stdin.read())
for k in path:
    if isinstance(d, list):
        d = d[int(k)] if int(k) < len(d) else None
    elif isinstance(d, dict):
        d = d.get(k)
    if d is None:
        break
print(d if d is not None else "")
' "$1"
}

# --- 1. resolve devme remote config ------------------------------------------
say "→ resolving devme remote config…"
STATUS_JSON=$(devme remote status --json 2>/dev/null) \
    || die "devme remote isn't configured or usable here.
  - set a host:        devme config set remote.host <ssh-target>
  - full preflight:    devme remote doctor"

HOST=$(printf '%s' "$STATUS_JSON" | jpath host)
RPATH=$(printf '%s' "$STATUS_JSON" | jpath remote_path)
SESSION=$(printf '%s' "$STATUS_JSON" | jpath session)
[ -n "$HOST" ] && [ -n "$RPATH" ] && [ -n "$SESSION" ] \
    || die "couldn't parse 'devme remote status --json' output"
URL_HOST=${HOST#*@}

# --- 2. locate the local Claude session --------------------------------------
SLUG=$(printf '%s' "$PWD" | sed 's/[^A-Za-z0-9]/-/g')
PROJ_DIR="$HOME/.claude/projects/$SLUG"
[ -d "$PROJ_DIR" ] || die "no Claude project dir at $PROJ_DIR
  run this from the directory the Claude session was started in"

if [ $# -ge 1 ] && [ -n "$1" ]; then
    SID=$1
    TRANSCRIPT="$PROJ_DIR/$SID.jsonl"
    [ -f "$TRANSCRIPT" ] || die "no transcript $TRANSCRIPT"
else
    # Newest non-subagent transcript == the session currently writing.
    TRANSCRIPT=$(ls -t "$PROJ_DIR"/*.jsonl 2>/dev/null | grep -v '/agent-' | head -1 || true)
    [ -n "$TRANSCRIPT" ] || die "no session transcript found under $PROJ_DIR"
    SID=$(basename "$TRANSCRIPT" .jsonl)
fi
say "→ session: $SID"

# --- 3. sync the working tree -------------------------------------------------
say "→ syncing working tree to ${HOST}…"
devme remote sync || die "devme remote sync failed (see above; try 'devme remote doctor')"

# --- 4. remote preflight --------------------------------------------------------
ssh -o BatchMode=yes "$HOST" true 2>/dev/null || die "cannot ssh to $HOST non-interactively"
ssh "$HOST" 'bash -lc "command -v claude"' >/dev/null 2>&1 \
    || die "claude is not installed on $HOST (curl -fsSL https://claude.ai/install.sh | bash)"
if ! ssh "$HOST" 'test -s ~/.claude/.credentials.json' 2>/dev/null; then
    say "⚠ no ~/.claude/.credentials.json on $HOST — the resumed session may sit at a login"
    say "  prompt. Fix once with 'claude setup-token' there, or complete /login in the pane."
fi

# Absolute remote project path (RPATH may be ~-relative) → remote slug.
RABS=$(ssh "$HOST" "cd $RPATH && pwd" 2>/dev/null) \
    || die "remote path $RPATH doesn't exist on $HOST yet — run 'devme remote' once to bootstrap"
RSLUG=$(printf '%s' "$RABS" | sed 's/[^A-Za-z0-9]/-/g')

# --- 5. copy transcript (+ project memory) ------------------------------------
# Ship a *prepared copy*, not the live transcript: a trailing user-message
# note tells the resumed session it now lives on the remote host and that
# every absolute path from earlier in the conversation refers to the old
# machine. The local transcript is left untouched (this session still
# writes to it).
PREP_DIR=$(mktemp -d /tmp/devme-remote-move.XXXXXX)
trap 'rm -rf "$PREP_DIR"' EXIT
PREPARED="$PREP_DIR/$SID.jsonl"
python3 - "$TRANSCRIPT" "$PREPARED" "$RABS" "$HOST" "$PWD" <<'PY' \
    || die "couldn't prepare the transcript copy"
import datetime, json, sys, uuid

src, dst, rabs, host, oldcwd = sys.argv[1:6]
lines = open(src).read().splitlines()

# Anchor the note onto the newest real entry so the chain stays intact.
parent = session_id = version = git_branch = None
for line in reversed(lines):
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    if d.get("uuid"):
        parent = d["uuid"]
        session_id = d.get("sessionId")
        version = d.get("version")
        git_branch = d.get("gitBranch")
        break

note = (
    "[devme-remote] This session was just moved from the laptop to the "
    f"remote host '{host}' and resumed inside the project's herdr session. "
    f"The project root changed from {oldcwd} to {rabs} — every absolute "
    "path mentioned earlier in this conversation refers to the old "
    "machine, so re-resolve files against the new root before reading or "
    "editing. All tools now run on the remote host (no ssh needed to "
    "reach it; the laptop is no longer reachable from here)."
)
entry = {
    "parentUuid": parent,
    "isSidechain": False,
    "userType": "external",
    "cwd": rabs,
    "sessionId": session_id,
    "version": version,
    "type": "user",
    "message": {"role": "user", "content": [{"type": "text", "text": note}]},
    "uuid": str(uuid.uuid4()),
    "timestamp": datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
}
if git_branch:
    entry["gitBranch"] = git_branch

with open(dst, "w") as f:
    f.write("\n".join(lines) + "\n")
    f.write(json.dumps(entry) + "\n")
PY
say "→ copying transcript to $HOST:~/.claude/projects/$RSLUG/…"
ssh "$HOST" "mkdir -p ~/.claude/projects/$RSLUG"
scp -q "$PREPARED" "$HOST:.claude/projects/$RSLUG/"
if [ -d "$PROJ_DIR/memory" ]; then
    scp -rq "$PROJ_DIR/memory" "$HOST:.claude/projects/$RSLUG/"
fi

# --- 5b. give the remote session its agent skills ------------------------------
# The resumed Claude runs inside a herdr pane (HERDR_ENV=1); the herdr skill
# is what lets it control panes/tabs from in there. Skills don't sync on
# their own, so ship our copy. devme's own skill installs from the remote
# binary (version-locked), so prefer that over copying ours.
ssh "$HOST" "mkdir -p ~/.claude/skills"
if [ -d "$HOME/.claude/skills/herdr" ]; then
    scp -rq "$HOME/.claude/skills/herdr" "$HOST:.claude/skills/" \
        || say "⚠ couldn't copy the herdr skill to $HOST (continuing)"
fi
ssh "$HOST" 'bash -lc "devme skill install --global --force"' >/dev/null 2>&1 \
    || say "⚠ couldn't install the devme skill on $HOST (continuing)"

# --- 6. seed the herdr session -------------------------------------------------
hssh() { ssh "$HOST" "env HERDR_SESSION=$SESSION $*"; }

WS_JSON=$(hssh "herdr workspace list" 2>/dev/null) || true
if [ -z "${WS_JSON:-}" ]; then
    ssh "$HOST" "command -v herdr" >/dev/null 2>&1 \
        || die "herdr is not installed on $HOST"
    say "→ starting herdr session server ($SESSION) on ${HOST}…"
    ssh "$HOST" "cd $RPATH && env HERDR_SESSION=$SESSION DEVME_URL_HOST=$URL_HOST sh -c 'nohup herdr server >/dev/null 2>&1 &'"
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        WS_JSON=$(hssh "herdr workspace list" 2>/dev/null) && break || true
    done
fi
[ -n "${WS_JSON:-}" ] || die "herdr session server didn't come up on $HOST"

WSID=$(printf '%s' "$WS_JSON" | jpath result.workspaces.0.workspace_id)
if [ -z "$WSID" ]; then
    hssh "herdr workspace create --cwd $RPATH --label $(basename "$RABS")" >/dev/null
    WS_JSON=$(hssh "herdr workspace list")
    WSID=$(printf '%s' "$WS_JSON" | jpath result.workspaces.0.workspace_id)
fi
[ -n "$WSID" ] || die "couldn't find or create a herdr workspace in session $SESSION"

say "→ opening 'claude' tab in herdr workspace ${WSID}…"
TAB_JSON=$(hssh "herdr tab create --workspace $WSID --label claude")
PANE=$(printf '%s' "$TAB_JSON" | jpath result.root_pane.pane_id)
[ -n "$PANE" ] || PANE=$(printf '%s' "$TAB_JSON" | jpath result.root_pane)
[ -n "$PANE" ] || die "couldn't parse the new tab's root pane id from: $TAB_JSON"

hssh "herdr pane run $PANE 'cd $RPATH && claude --resume $SID'"

# --- 7. verify the resume took -------------------------------------------------
sleep 4
PANE_OUT=$(hssh "herdr pane read $PANE --source recent --lines 25" 2>/dev/null || true)
case "$PANE_OUT" in
    *"No conversation"*|*"command not found"*)
        say "⚠ the remote pane shows a problem:"
        printf '%s\n' "$PANE_OUT" >&2
        die "resume did not start cleanly — attach with 'devme remote' to inspect"
        ;;
esac

printf '\n✅ Claude session moved to %s (herdr tab \"claude\", pane %s).\n' "$HOST" "$PANE"
printf 'Close this session and run `devme remote` to pick it up where you left off.\n'
