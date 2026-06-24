# Sanitas Demo Decisions

Sanitas is a medicine supply risk intelligence platform for seeing medicine availability risk before it reaches patients. The hackathon demo should make the graph feel like the product itself: a command-center view where supply-chain dependencies, evidence, and risk propagation are visible and explorable.

## Demo Story

The pitch can start with a representative patient story to make the stakes human, but the product does not model individual patients. The system view is for hospital pharmacy, supply, or risk teams who need to understand medicine availability before a shortage affects care.

The demo should move from system awareness to focused explanation:

1. The user opens Sanitas and sees a broad medicine risk network.
2. One critical medicine is already glowing in a warning color.
3. The presenter clicks that medicine.
4. The graph morphs into a focused risk path for that medicine.
5. The right panel explains the risk profile, care impact, evidence, and recommended action.
6. A scripted agent investigation adds one new evidence source and updates confidence or risk modestly.

## Product Name

The product name is **Sanitas**.

The working tagline is:

> See medicine supply risk before it reaches patients.

## Main Route

The main product experience lives at `/`. There should be no marketing hero page before the graph. `/dashboard` can remain as an alias if convenient, but `/` is the judged demo route.

## Visual Direction

The UI should feel like a dark command-center and supply-chain intelligence surface with subtle medical cues. It should not feel like a clinical patient app or a marketing page.

Use a clean graph-first layout:

- Dark mode.
- Minimal top chrome.
- Risk is primarily shown through color, glow, and emphasis.
- Avoid text-heavy risk labels on every node.
- Keep labels visible only where they help the story.
- Use hover, click, and the right panel for detail.
- The graph should be visually impressive but still explainable in seconds.

## Network Overview

The first state is the **Network Overview**, a broad view of the Medicine Risk Network.

Recommended composition:

- About seven medicines near the center.
- One critical medicine glowing red from the start.
- Two elevated medicines.
- Two watch medicines.
- Two stable medicines.
- Upstream dependencies, places, events, and evidence farther from the center.
- Shared dependencies should be visible enough to prove why a graph is useful.

The overview is a real overview, not only a cinematic splash screen, but it does not need full filters or complete analysis tooling for the hackathon.

## Focused Medicine Risk Graph

Clicking the critical medicine transitions into the focused **Medicine Risk Graph**.

The focused view should show the active risk path only:

```text
Medicine -> component/API -> supplier -> place -> event -> evidence
```

The transition should happen on the same page. Try a true morph if feasible:

- Shared node IDs move from overview coordinates to detail coordinates.
- Unrelated nodes fade or scale down.
- The selected medicine remains the anchor.
- The selected risk path brightens.
- The right panel opens.

If true morphing becomes risky, use a polished zoom/crossfade that preserves the selected medicine as the anchor.

## Right Panel

Clicking or focusing a node opens a fixed right-side investigation panel on desktop. On mobile it can become a bottom sheet.

When the focused medicine first opens, the panel should show the medicine-level Risk Profile:

- Supply fragility.
- Demand pressure.
- Evidence strength or confidence.
- Evidence count.
- Care Impact.
- Recommended action.

When a node is selected, the panel should prioritize relevance:

1. Why this node matters for the selected medicine.
2. Risk contribution, confidence, or evidence count.
3. Evidence sources.
4. Facts.
5. Suggested agent investigations and a small input.

## Evidence Sources

Sources are shown as small **Evidence Satellites** attached to the node they support. Relevant evidence can be larger or brighter.

Clicking an Evidence Satellite should not immediately leave the app. It opens the right panel first. The panel has a deliberate **Open source** action for live external navigation.

The final medicine case should use a real medicine and real sources. Until that case is chosen, use replaceable placeholder data.

## Agent Investigation

The demo uses a scripted investigation replay. The supplier chain should already be mapped before the user starts an investigation.

The live agent moment should add evidence, not discover a new major supplier-chain branch.

Scripted flow:

1. User clicks a suggested action such as **Find newer evidence**.
2. The panel shows a short progress sequence.
3. One new Evidence Satellite animates into the graph.
4. A new connection is drawn.
5. Confidence, evidence count, or risk score changes modestly.
6. The Risk Path pulses once.
7. The Graph Change Timeline records what changed.

The interaction should make the system feel alive without implying the original graph was incomplete.

## Recommendation Copy

The scripted recommendation for the focused state is:

> **Prepare alternate supplier order**
> Verify approved supplier availability and lead time before stock falls below safety threshold.

This is intentionally operational and modest. Avoid copy that implies the system makes clinical or procurement decisions automatically.

## Demand Signals

The product can reason about both supply-side risk and demand-side pressure. For the main demo, demand can appear as stable in the Risk Profile. Do not add demand nodes to the focused graph unless demand is an active risk driver.

## Data Shape

Keep the demo data simple and replaceable:

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

Keep richer side-panel data in a lookup by node ID:

```ts
type NodeDetails = Record<
  string,
  {
    whyItMatters: string;
    facts: string[];
    sources: { title: string; url: string; meta: string }[];
    prompts: string[];
  }
>;
```

The graph data should stay compatible with later Neo4j-backed data, but the demo layout can use handcrafted coordinates for polish.

## Explicit Cuts

Do not build these for the first demo pass:

- No patient data or patient nodes.
- No full live scraping dependency in the judged path.
- No arbitrary automatic graph layout requirement.
- No fully freeform chatbot requirement.
- No discovery of new supplier-chain branches during the scripted investigation.
- No complex filters.
- No full dashboard shell around the graph.

## Open Later

These decisions can wait:

- Exact medicine case.
- Exact real evidence sources.
- Final label density.
- Final animation library.
- Whether `/dashboard` remains as a public alias.
- Full Neo4j schema and ingestion pipeline.
