# Sunstead Remotion video

<p align="center">
  <a href="https://github.com/remotion-dev/logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-dark.apng">
      <img alt="Animated Remotion Logo" src="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-light.gif">
    </picture>
  </a>
</p>

Remotion project for hackathon demo animation and cinematic video assets.

This package is part of the root Bun workspace. Prefer running commands from the
repo root so installs, scripts, and agent context stay consistent.

## Commands

**Install Dependencies**

```console
bun install
```

**Start Preview**

```console
bun run video:dev
```

**Render video**

```console
bun run video:render
```

**Upgrade Remotion**

```console
bun run --filter video-remotion upgrade
```

**Lint and typecheck**

```console
bun run video:lint
```

## Docs

Get started with Remotion by reading the [fundamentals page](https://www.remotion.dev/docs/the-fundamentals).

## Agent skills

Before editing Remotion code, load the local skill:

```console
video-remotion/.codex/skills/remotion-best-practices/SKILL.md
```

For this project, the most relevant rules are usually:

- `rules/video-layout.md` for cinematic composition and text sizing
- `rules/sequencing.md` for scene timing
- `rules/videos.md` and `rules/audio.md` for recorded/downloaded footage
- `rules/transparent-videos.md` for ProRes alpha exports into external editors
- `rules/transitions.md`, `rules/light-leaks.md`, and `rules/effects.md` for polish

## Help

We provide help on our [Discord server](https://discord.gg/6VzzNDwUwV).

## Issues

Found an issue with Remotion? [File an issue here](https://github.com/remotion-dev/remotion/issues/new).

## License

Note that for some entities a company license is needed. [Read the terms here](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md).
