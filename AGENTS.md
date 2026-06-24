<!--VITE PLUS START-->

# Using Vite+, the Unified Toolchain for the Web

This project is using Vite+, a unified toolchain built on top of Vite, Rolldown, Vitest, tsdown, Oxlint, Oxfmt, and Vite Task. Vite+ wraps runtime management, package management, and frontend tooling in a single global CLI called `vp`. Vite+ is distinct from Vite, and it invokes Vite through `vp dev` and `vp build`. Run `vp help` to print a list of commands and `vp <command> --help` for information about a specific command.

Docs are local at `node_modules/vite-plus/docs` or online at https://viteplus.dev/guide/.

## Dev Server Workflow

DevMe is the only supported way to run development servers in this repo. Do not
start long-running servers with `vp dev`, `bun run dev`, `vp run storybook`, or
`storybook dev` directly. Those commands create unmanaged processes on fixed
ports and make multi-agent work confusing.

Use DevMe for runtime state, URLs, logs, and restarts:

- Start/repair services with `devme up -d`.
- Check what is running with `devme status`.
- Open services with `devme url web` and `devme url storybook`.
- Read logs with `devme logs <service> --since 5m`, `devme logs --since 5m`,
  or `devme doctor`.
- Restart stale services with `devme restart web` or `devme restart storybook`.

Ports are slot-aware. Do not assume `3000` or `6006`; use `devme status` or
`devme url <service>` every time.

## Review Checklist

- [ ] Run `vp install` after pulling remote changes and before getting started.
- [ ] Run `vp check` and `vp test` to format, lint, type check and test changes.
- [ ] Check if there are `vite.config.ts` tasks or `package.json` scripts necessary for validation, run via `vp run <script>`.
- [ ] If setup, runtime, or package-manager behavior looks wrong, run `vp env doctor` and include its output when asking for help.

<!--VITE PLUS END-->
