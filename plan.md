# Sanitas Dashboard Build Plan

## Goal

Build the first polished Sanitas demo surface at `/`: a dark graph-first command view that opens on a broad medicine risk network, then transitions into a focused medicine risk graph for one critical medicine.

The goal is visual demo quality first. Use scripted data and scripted investigation replay, but keep the data shape replaceable so real Neo4j-backed graph data can be connected later.

## References

- `CONTEXT.md`: domain language.
- `docs/sanitas-demo-decisions.md`: product and demo decisions.
- `docs/adr/0001-scripted-investigation-replay-for-demo.md`: why the demo path is scripted.
- `src/routes/index.tsx`: main route, currently renders the graph experience.
- `src/routes/dashboard.tsx`: current graph data and top-level screen.
- `src/ui/supply-risk.tsx`: current graph renderer.
- `src/styles.css`: current graph styling.

## Current State

`/` already renders the existing focused graph view. The old hero page has been removed from the route. The current view is visually close to the desired focused Medicine Risk Graph, but it does not yet have the Network Overview, transition, right panel, or scripted agent investigation.

## Build Sequence

### 1. Extract Demo Data

Create a small data module or local data section for graph data.

Use the simple graph shape:

```ts
type GraphNode = {
  id: string;
  kind: "medicine" | "component" | "supplier" | "place" | "event" | "source";
  label: string;
  risk: "critical" | "elevated" | "watch" | "stable";
  summary: string;
  overview: { x: number; y: number };
  detail?: { x: number; y: number };
};

type GraphEdge = {
  from: string;
  to: string;
  risk: "critical" | "elevated" | "watch" | "stable";
};
```

Use placeholder medicine data for now. Keep Meropenem IV as the critical medicine unless a better real case is provided before implementation.

Acceptance criteria:

- Data is easy to replace.
- Overview and detail layouts share node IDs.
- Source/evidence nodes are represented as graph nodes with kind `source`.

### 2. Build View State

Add explicit view state to the graph screen:

```ts
type GraphMode = "overview" | "focused";
```

Track:

- selected medicine ID.
- selected node ID.
- whether investigation is running.
- whether scripted evidence has been added.

Acceptance criteria:

- `/` opens in `overview`.
- Clicking the critical medicine switches to `focused`.
- The selected medicine remains the visual anchor.

### 3. Create Network Overview

Replace the initial focused-only layout with a radial-style overview.

Recommended layout:

- Medicines near the center.
- Components and suppliers in an inner/middle ring.
- Places, events, and sources farther out.
- One critical medicine glows red.
- Calm nodes are lower emphasis.

Acceptance criteria:

- About seven medicines are visible.
- One critical medicine is clearly clickable and pre-attentive.
- Shared dependencies are visible enough to explain why graph modeling matters.
- Top bar is minimal and overview-specific.

### 4. Add Focus Transition

Implement the click transition from Network Overview to focused Medicine Risk Graph.

Preferred behavior:

- Try a true morph using explicit coordinates.
- Animate node position, opacity, scale, and emphasis.
- Fade unrelated nodes.
- Brighten the active Risk Path.
- Draw or emphasize focused edges.

Fallback behavior:

- Use a polished zoom/crossfade between overview and focused positions.
- Keep the selected medicine as the anchor.

Acceptance criteria:

- Transition happens on the same page.
- No hard navigation is required.
- The focused risk path is obvious after the transition.

### 5. Refine Top Bar

Make the top bar context-aware.

Overview state:

- `Sanitas`
- Search placeholder such as `Search medicines, suppliers, sources...`
- Summary such as `1 critical path`
- Agent/timeline icon

Focused state:

- `Sanitas`
- Search value with selected medicine name
- Summary such as `87 critical`
- Agent/timeline icon
- `Investigate latest evidence` action

Acceptance criteria:

- Top chrome stays minimal.
- The focused state clearly reflects the selected medicine.
- Remove anything that feels like a toy simulation label.

### 6. Add Right Panel

Add a fixed right-side panel on desktop.

Focused medicine state should show:

- Risk Profile.
- Care Impact.
- Recommendation.
- Evidence count and confidence.

Selected node state should show:

- Why this node matters.
- Risk contribution or confidence.
- Evidence sources.
- Facts.
- Suggested investigation prompts.
- Small input area.

Acceptance criteria:

- Panel opens when entering focused mode.
- Clicking a node updates the panel.
- The graph remains spatially stable when the panel opens.
- Panel copy is concise and operational.

### 7. Add Hover Preview

Add lightweight hover previews for graph nodes.

Preview should show:

- node label.
- node kind.
- risk level by color.
- one-line summary.

Acceptance criteria:

- Hover preview does not shift layout.
- Preview is readable but does not compete with the side panel.
- Click remains the primary detail action.

### 8. Add Evidence Satellite Behavior

Treat source nodes as compact evidence satellites.

Behavior:

- Evidence Satellites are small.
- Relevant evidence can be brighter or slightly larger.
- Clicking a source opens its detail in the right panel.
- External navigation happens only through an explicit `Open source` button.

Acceptance criteria:

- Source nodes do not dominate the graph.
- Source click keeps the user inside the app.
- Open source action is clear in the panel.

### 9. Add Scripted Agent Investigation

Script one investigation action.

Flow:

1. User clicks `Find newer evidence`.
2. Show progress steps in the panel.
3. Animate in one new Evidence Satellite.
4. Draw one new connection.
5. Update confidence or evidence count.
6. Pulse the Risk Path.
7. Add entries to a Graph Change Timeline.

Acceptance criteria:

- The supplier chain does not change during the investigation.
- The investigation adds evidence only.
- The update is modest and credible.
- The animation finishes quickly enough for a live demo.

### 10. Responsive Pass

Make desktop the hero experience, but keep mobile coherent.

Acceptance criteria:

- Desktop graph has no major overlap at the default viewport.
- Mobile can show a vertical graph or simplified layout.
- Top bar controls do not overflow.
- Right panel becomes a bottom sheet or full-screen detail layer on mobile.

### 11. Verification

Run:

```bash
vp test
vp check
```

If `vp check` is blocked by unrelated pre-existing formatting or Storybook issues, format only files touched by this work and report the blocker clearly.

Use DevMe for service work:

```bash
devme status
devme url web
```

Do not run `vp dev` or `bun run dev` directly.

Browser-verify:

- `/` opens in overview mode.
- Clicking the critical medicine transitions to focused mode.
- Right panel opens.
- Node hover preview works.
- Node click updates panel.
- Scripted investigation adds evidence and updates the timeline.

## Demo Copy

Recommendation:

> Prepare alternate supplier order
> Verify approved supplier availability and lead time before stock falls below safety threshold.

Care Impact example:

> Used in time-sensitive hospital treatment where delayed availability can affect patient care.

Investigation prompts:

- Find newer evidence.
- Explain risk path.
- Check demand pressure.
- Review alternate supplier readiness.

## Non-Goals

- Do not build a marketing landing page.
- Do not add patient nodes.
- Do not depend on live scraping for the main demo path.
- Do not build arbitrary graph auto-layout.
- Do not build a fully freeform chatbot.
- Do not discover new supplier-chain nodes during the scripted investigation.
- Do not overbuild filters or dashboard chrome.
