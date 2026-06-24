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
