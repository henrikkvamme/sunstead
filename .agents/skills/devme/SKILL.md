---
name: devme
description: Manage dev environments with devme. Use when services fail, won't start, crash-loop, show errors, databases are down, Docker isn't running, or user asks "what's wrong", "fix the environment", "check status", "restart", "logs", or mentions devme. Also use for `/devme setup` to generate a devme.toml for a new project, and for devme remote workflows.
license: MIT
metadata:
  version: "0.1.0"
allowed-tools: Bash(devme *) Bash(docker *) Bash(lsof *) Bash(ps *) Bash(find *) Bash(cat *) Bash(ls *) Bash(bash ~/.agents/skills/devme/scripts/move-session.sh*) Read Write
---

## devme: $action

Route on `$action`. Default to diagnostics when none is given.

---

### action "doctor" or empty — diagnose and fix

1. Run `devme doctor`. It returns an error-anchored JSON digest: per-service state/pid/port/restart count + `recent_errors` (stderr only — tracebacks, not access logs), and step states with a *failed* step's check/provision output inline. History is disk-backed, so a service that crashed an hour ago still shows its dying stderr. Summarize for the user; don't dump raw. (`status: "no_daemon"` → tell them to run `devme up -d`.)
2. Zoom with `devme doctor <name>` — for a failed step it returns the full check/provision output (the **only** place step output surfaces); for a service, `recent_errors` + `recent_logs` (`[stderr]`-prefixed). Then fix:
   - Container name conflict ("already in use") → `docker rm -f <name>`, then `devme restart <svc>`
   - Port conflict ("address already in use") → `lsof -ti :<port> | xargs kill -9`, then `devme restart <svc>`
   - Docker not running → `devme config set docker.daemon orbstack`, then `devme up -d`
   - Failed step → fix the cause, then `devme restart <dependent>` (step states gate dependent services)
3. Confirm with `devme doctor`.

### action "logs" — read service logs

- `devme logs <svc> --tail 100` — one service. `devme logs` (no name) — **all services interleaved by timestamp**, the fastest way to see cross-service causality ("api 500s right after postgres restarted").
- `devme logs --since 5m` (`30s`/`2h`/`1d`/epoch-ms) — "what happened since my last check"; disk-backed, so it works even after the daemon restarted. Prefer `--since` over guessing a `--tail` count.
- `devme logs --json` — NDJSON `{ts, service, stream, text}` (ANSI-stripped), pipe to jq: `devme logs --json --since 10m | jq -c 'select(.stream == "stderr")'` is the cheapest error sweep.
- Each line is stream-tagged: errors/tracebacks live on `stderr`, routine chatter on `stdout` — filter on that before reading everything.
- `logs` is **services only**: `devme logs <step>` errors and points you to `devme doctor <step>`, where step check/provision output lives. Unknown names error immediately — don't wait for output that will never come.

### action "setup" — generate devme.toml

Detect the stack from `package.json` (scripts.dev, drizzle/prisma), `Cargo.toml`, `pyproject.toml`/`requirements.txt`, `go.mod`, `docker-compose.yml`, `Dockerfile`, `.env`/`.env.example`, and DB references. Then write a `devme.toml`:

```toml
schema_version = 1

# Env: devme prompts for missing values on first run, writes to .env.local.
[env.DATABASE_URL]
required = true
default = "postgresql://user:pass@localhost:5432/mydb"
help = "Connection string for the dev database"   # tell the user where to find it
[env.SECRET_KEY]
generate = "openssl rand -hex 32"                 # auto-create secrets
[env.REGION]
choices = ["us-east-1", "eu-west-1"]              # known option set
default = "eu-west-1"

# Steps: prerequisites checked before services start. check returns 0 on success;
# provision runs to fix a failing check. trust gates consent for provision:
#   prompt (default) — ask first   auto — run unattended   manual — show, never run
[step.bun]
check = "command -v bun"
provision = "curl -fsSL https://bun.sh/install | bash"
[step.deps]
check = "test -d node_modules"
provision = "bun install"
trust = "auto"
depends_on = ["bun"]

# Services: long-running. {port} = slot-aware allocation.
[service.postgres]
cmd = "docker rm -f myapp-pg 2>/dev/null; docker run --rm --name myapp-pg -e POSTGRES_USER=dev -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=mydb -p {port}:5432 postgres:17-alpine"
port = { base = 5432, slot_offset = 10 }
[service.web]
cmd = "bun run dev"
port = { base = 3000, slot_offset = 10 }
url = "http://{host}:{port}"
depends_on = ["deps"]
```

Rules:
- `bun` for JS/TS (not npm/node).
- Docker services: prefix `cmd` with `docker rm -f <name> 2>/dev/null;` and run `--rm --name <project>-<service>` to survive stale containers.
- **Web services (dev servers, frontends, APIs) need `url = "http://{host}:{port}"`** — it's the only signal that a `host:port` is openable. Without it devme treats the service as copy-only (DB/TCP), so the TUI's `o` and `devme url -o` won't open a browser. DBs/TCP services: omit `url`.
- Dep-install steps: `trust = "auto"`, depend on the runtime step. Privileged fixes (`sudo`, Xcode CLT): `trust = "manual"` (devme can't answer sudo/GUI prompts). Migrations: depend on both `deps` and the DB service.
- Run `devme config check` after writing — it flags cycles, unknown deps, and web services missing a `url`.

---

### action "remote-session" — move an agent session to the remote host

Use this only when the user explicitly asks to move the current local agent
session to the devme remote host/VPS, e.g. "continue this on the server",
"move this session to the VPS", or "teleport this session".

For normal remote development, prefer `devme remote` and the remote commands in
the CLI reference. This action is narrower: it syncs the current working tree,
copies the current agent transcript to the remote project, and opens a Herdr tab
there so the user can attach with `devme remote`.

Run from the project root:

```bash
bash ~/.agents/skills/devme/scripts/move-session.sh
```

Pass an explicit session id as `$1` only if the user names one.

Stream the script output to the user. On success, stop work immediately and tell
the user to close the local session and run `devme remote`; the remote session
forks from the local transcript at the moment it resumes.

Caveats:
- This is copy-and-resume, not live migration. The local and remote sessions can
  diverge after the move.
- File checkpoints/rewind state do not travel; only the conversation transcript
  and project memory do.
- The bundled script currently targets Claude Code transcript/layout paths. For
  Codex/Pi sessions, use `devme remote` directly until a dedicated mover exists.

---

### CLI reference

| Command | Purpose |
|---------|---------|
| `devme doctor [<name>] [--tail N]` | JSON error digest: states + stderr-only `recent_errors` per service, failed-step output inline. `<name>` zooms into one step (full check/provision output) or service |
| `devme status [--all]` | Grouped STEPS/SERVICES snapshot: state glyph, resolved URL, pid, restart count, plus a warning footer naming any unhealthy service. Mid-`up`, blocked services show `waiting on <dep>` (not `stopped`); repo-shared (`scope = "repo"`) services show the shared supervisor's true state. `--all` = state-glyph + port matrix across every worktree (`*` = current). `--json` for structured: `services[].state.kind` (`running`/`starting`/`waiting_on_dependency` + `blocked_by`/`failed`/…), resolved `url`, `pid`, `port` |
| `devme logs [<svc>] [--tail N] [--since 5m] [--json] [-f]` | Service log streams (disk-backed history). No name = all services interleaved by ts; `--json` = NDJSON `{ts, service, stream, text}` for jq; steps are refused (→ doctor) |
| `devme url <svc> [-o]` | Print a service's URL; `-o` opens it in the browser |
| `devme start/stop/restart <svc>` | Lifecycle a single service |
| `devme up -d` / `up -y` / `down [--all]` | Start all detached / start running `prompt` provisions unattended (CI) / stop this worktree's stack (`--all` = every worktree, like `status --all`) |
| `devme worktree add <branch> [path]` | New worktree (+branch), ready for `devme up` (steps converge it — no setup hook). Default path `<repo>-<branch-leaf>` |
| `devme worktree rm <target>` | Stop stack, `git worktree remove`, release the port slot. Target by path/dir/branch; `-f` forces dirty. Branch + commits are kept |
| `devme config [set <k> <v>] [check]` | Show / set global config; `check` lints `devme.toml` (`--json`, non-zero on errors) |
| `devme remote [doctor\|status\|conflicts\|sync\|flush\|stop\|wake\|toggle]` | Live-sync to `remote.host` and run the stack there — see remote note. `doctor` preflights; resolve `conflicts` before changes flow. `status --watch` (`-w`) refreshes a one-line sync state for a side pane. `toggle` flips `remote.default` — whether bare `devme` is local or remote-first |
| `devme --local <cmd>` | Force a command against the local daemon, bypassing the remote proxy |
| `devme skill install [-g]` | (Re)install this skill into `.Codex/skills/devme/` (`-g` = `~/.Codex/`); embedded, always matches the binary |

### Notes

- **Which command answers which question.** `devme config check` = "is the toml valid" (static). `devme status` = "what's running where" (states + ports, no logs). `devme logs` = "what are the services saying" (runtime streams only). `devme doctor` = "why is it broken" (error digest + step output). Don't read full logs to find errors — `doctor` or a `--json` stderr filter is cheaper.
- **Worktree-aware.** Each git worktree runs its own supervisor, slot, and ports. `up`/`down`/`doctor`/`status`/`logs`/`url` act on the worktree you're in — just call them. `devme down --all` stops every worktree's stack (and the shared services); `devme status --all` shows every worktree's ports; `devme url <svc>` gives a ready link without guessing the slot.
- **Worktrees converge — no lifecycle hooks.** There is no per-worktree setup or teardown hook (`[stack] on_create`/`on_destroy` parse for back-compat but never run — `config check` flags them). Per-worktree setup is a `[step]` check/provision: idempotent, so *any* worktree — created by `devme worktree add`, the TUI's `w`, or a bare `git worktree add` — converges on its first `devme up`. Removal is mechanical (stop, `git worktree remove`, release slot); a bare `git worktree remove` is reaped to the same end state. Make slot-scoped provisions idempotent (e.g. `dropdb --if-exists app_slot{slot} && createdb app_slot{slot}`) so a reused slot starts clean.
- **Restart cascades.** Services have dependency ordering; restarting a DB can cascade to dependents.
- **Remote is remote-primary.** The supervisor, stack, and TUI run on `remote.host`; the laptop syncs files (Mutagen `two-way-safe` — a conflict *halts* the sync). It syncs the **main** worktree only; create worktrees on the host (worktree *metadata* is per-machine and never synced). Starting a sync requires a project root (a `devme.toml` or git repo) — `devme remote` refuses a bare directory. `devme remote --no-input` fails closed if the remote stack would prompt (env wizard), so agents never hang on it. While a sync is live, daemon commands (`status`, `logs`, `up`, `doctor`, `url`, …) auto-run on the remote — `devme logs api` streams the host's logs, and `devme url` rewrites to a laptop-reachable host. Run `devme remote doctor` before the first attach; if `devme remote status` shows conflicts the sync is halted — fix them first. While you're attached, `devme remote` watches the sync in the background and desktop-notifies if it halts (you can't see it from the remote TUI), and prints a closing sync summary on detach.
