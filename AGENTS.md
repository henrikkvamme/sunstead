# Agent Context

This repo uses Vite+ (`vp`) with Bun. Use `vp install` after pulling changes,
then `vp check` and `vp test` before handing off code. Use `vp build` when the
change touches build behavior.

DevMe owns all long-running services. Use the DevMe skill for runtime work,
logs, restarts, broken services, port questions, and environment debugging.

- Start or repair services with `devme up -d`.
- Check state with `devme status`.
- Open services with `devme url web` and `devme url storybook`.
- Read logs with `devme logs <service> --since 5m`, `devme logs --since 5m`,
  or `devme doctor`.
- Restart stale services with `devme restart web` or `devme restart storybook`.

Do not run `vp dev`, `bun run dev`, `vp run storybook`, or `storybook dev`
directly. DevMe assigns slot-aware ports, so never assume `3000` or `6006`.
Use `devme status` or `devme url <service>` every time.

When doing browser-based visual work, prefer the user's configured browser/Chrome
MCP if it is exposed in the current tool list. If it is not exposed, use
Playwright as a fallback for public pages and local routes, save screenshots or
scrape artifacts under `/tmp`, and do not commit those artifacts.

Storybook must stay isolated from the app's TanStack Start Vite plugins. Keep
Storybook pointed at `.storybook/vite.config.ts` and add only the minimal
Storybook Vite config needed for Tailwind and path aliases.

If `vp check` fails because of an unrelated pre-existing or untracked file, do
not format or modify that file unless the task asks for it. Format/check the
files touched for the task, run `vp lint`, `vp test`, and `vp build` as
appropriate, and report the unrelated blocker clearly in the handoff.

## UI components

Use the shared dashboard kit in `src/ui/dashboard.tsx` when building app-shell,
dashboard, admin, monitoring, or agent-workflow screens. Route files should
compose data with `AppDashboardShell`, `DashboardModuleSection`,
`AppDashboardGrid`, `AppDashboardPanel`, and the related helpers from
`#/ui/dashboard` instead of recreating sidebar, topbar, panel, chart, token, or
agent-integration chrome locally.

## Agent skills

This repo uses the globally installed Matt Pocock workflow skills rather than
checking duplicate skill copies into `.agents/skills/`. The project-specific
routing context those skills need lives in `docs/agents/`.

Use the workflow skills for their matching jobs:

- `triage`, `to-issues`, and `to-prd` for Linear issue flow.
- `tdd` and `diagnose` for implementation and debugging loops.
- `domain-modeling`, `grill-with-docs`, `zoom-out`, and
  `improve-codebase-architecture` for domain language and architecture work.
- `setup-matt-pocock-skills` only if the `docs/agents/` routing files are
  missing or stale.

### Issue tracker

Issues are tracked in Linear workspace `Sunstead Goblins`, team `SUN`. See `docs/agents/issue-tracker.md`.

### Triage labels

Linear uses the five canonical triage labels for agent workflow. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain docs layout. See `docs/agents/domain.md`.
