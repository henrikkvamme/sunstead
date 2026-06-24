# Sunstead

```bash
curl -fsSL https://devme.sh/install | sh
devme skill install
devme
```

DevMe installs the tools, installs the agent skill, starts the app, assigns
ports, and shows logs.

## Services

```bash
devme status
devme url web
devme url storybook
devme logs --since 5m
devme doctor
```

Do not start servers with `vp dev`, `bun run dev`, or `storybook dev` directly.
Ports are slot-aware, so use `devme url <service>` instead of guessing.

## Checks

```bash
vp check
vp test
vp build
```

## Stack

- TanStack Start + TanStack Router
- Vite+ and Bun
- Tailwind CSS v4
- Storybook

## Files

- `src/routes/index.tsx`: main page
- `src/styles.css`: global styles
- `src/ui/index.tsx`: UI primitives
- `src/ui/stories/components.stories.tsx`: Storybook stories
