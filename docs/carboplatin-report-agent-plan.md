# Carboplatin Report Agent Plan

## Purpose

Create the report experience that appears after the scripted AI investigation reaches `report-ready`. The report is for a hospital pharmacy or supply-risk team watching the Carboplatin Injection risk path. It must be credible enough to feel like a real Sanitas output, but simple enough to understand in a few seconds in the demo video.

The report should not model the patient. The patient story belongs in narration. The product report models medicine supply risk and operational response.

## Demo Constraint

The report will be visible briefly, so it needs one dominant message:

> Carboplatin Injection has an active shortage signal, with the clearest action path tied to FDA shortage evidence, Accord / Intas supplier constraints, and GMP compliance requirements. Prepare alternate supplier ordering before stock falls below safety threshold.

Avoid a dense research memo. The viewer should be able to read the top half of the report almost instantly.

## Current Graph Contract

Use the existing scenario data in `src/data/carboplatin-risk-scenario.ts`.

Important IDs:

- Medicine: `med-carboplatin`
- Main warning event: `event-fda-shortage`
- Main supplier path: `supplier-accord-intas`
- Main constraint: `event-gmp`
- Scripted new evidence event: `event-api-shortage-2026`
- Scripted new source: `source-times-india-2026`

The report should preserve the same single action path used by the graph:

```text
Carboplatin Injection -> FDA current shortage -> Accord / Intas -> GMP compliance constraint
```

Context branches may appear as supporting material, but they must not become a second red storyline. API pressure, South African platinum supply, demand increase, shipping delay, discontinued presentations, and other suppliers are context signals only.

## Recommended On-Screen Report

Use a compact report preview, not a full document page. It should feel like a generated hospital decision brief.

Suggested layout:

1. Header row
   - Title: `Carboplatin Injection Supply Risk Brief`
   - Status pill: `Action needed`
   - Timestamp or freshness line: `Prepared from mapped evidence`

2. One-sentence finding
   - `Active shortage evidence and a supplier quality constraint create a high-risk path for hospital-ready carboplatin supply.`

3. Risk path strip
   - Four inline nodes with arrows:
   - `Carboplatin Injection`
   - `FDA current shortage`
   - `Accord / Intas`
   - `GMP compliance constraint`

4. Evidence chips
   - `FDA shortage record`
   - `ASHP shortage detail`
   - `Times of India API report`
   - Optional small text: `Primary + clinical + recent supporting evidence`

5. Recommended action
   - Heading: `Recommended action`
   - Copy: `Prepare alternate supplier order. Verify approved supplier availability and lead time before stock falls below safety threshold.`

6. Operational checklist
   - `Check approved alternatives`
   - `Confirm lead times`
   - `Review current stock and safety threshold`
   - `Escalate oncology allocation policy only if inventory drops`

Keep the first screen to roughly 80-120 words. More detail can exist below the fold or in expandable sections, but the demo should not depend on scrolling.

## Evidence Priority

Rank sources by how directly they support the action.

Primary evidence:

- FDA Carboplatin Injection shortage page
  - Use for current shortage status and supplier-level reasons.
  - This is the evidence anchor.

- ASHP Carboplatin Injection shortage page
  - Use for clinical pharmacy shortage context.
  - This supports hospital relevance.

Supporting recent evidence:

- Times of India May 2026 API report
  - Use as the scripted investigation's newly added supporting evidence.
  - Present as an upstream API-risk signal, not as the primary proof of the U.S. shortage.

Background context:

- Axios 2023 cancer shortage article
- NCCN/Health survey coverage
- Financial Times Intas / cancer drug shortage analysis
- MarketWatch platinum market context

Do not make the 2023 articles look like the current shortage proof. They are useful for stakes and historical care impact, but the report should lead with FDA/ASHP and the 2026 source.

## Report Data Shape

Create a small frontend data model that can later be replaced by the real AI module. Keep it close to the graph data, not a separate invented schema.

Suggested shape:

```ts
type SupplyRiskReportPreview = {
  id: string;
  medicineId: string;
  title: string;
  status: "action-needed" | "watch" | "stable";
  generatedAtLabel: string;
  headlineFinding: string;
  actionPathNodeIds: string[];
  evidenceSourceNodeIds: string[];
  recommendedAction: {
    title: string;
    summary: string;
    checklist: string[];
  };
  confidence: {
    label: string;
    rationale: string;
  };
  caveats: string[];
};
```

Initial values:

```ts
{
  id: "report-carboplatin-demo",
  medicineId: "med-carboplatin",
  title: "Carboplatin Injection Supply Risk Brief",
  status: "action-needed",
  generatedAtLabel: "Prepared from mapped evidence",
  headlineFinding:
    "Active shortage evidence and a supplier quality constraint create a high-risk path for hospital-ready carboplatin supply.",
  actionPathNodeIds: [
    "med-carboplatin",
    "event-fda-shortage",
    "supplier-accord-intas",
    "event-gmp",
  ],
  evidenceSourceNodeIds: [
    "source-fda-carboplatin",
    "source-ashp-carboplatin",
    "source-times-india-2026",
  ],
  recommendedAction: {
    title: "Prepare alternate supplier order",
    summary:
      "Verify approved supplier availability and lead time before stock falls below safety threshold.",
    checklist: [
      "Check approved alternatives",
      "Confirm lead times",
      "Review current stock and safety threshold",
      "Escalate oncology allocation policy only if inventory drops",
    ],
  },
  confidence: {
    label: "High",
    rationale:
      "Current shortage evidence is backed by primary shortage sources; API evidence is supporting context.",
  },
  caveats: [
    "Patient impact is narration only and not represented as patient-level data.",
    "Upstream platinum and API signals are risk amplifiers, not the direct proven cause.",
  ],
}
```

## Visual Direction

The report should feel like a decision brief inside the existing dark command-center UI.

Use:

- A compact panel or sheet connected to the existing `report-ready` state.
- One strong red/orange `Action needed` marker.
- The same action-path colors used by the graph.
- Evidence chips with source type labels, not long URLs.
- Small caveat text so the product feels careful, not overconfident.

Avoid:

- A legal-document layout.
- Large paragraphs.
- Patient cards or patient identifiers.
- A second red path for API or platinum context.
- Claims that Sanitas has automatically made the procurement or clinical decision.

## Suggested Copy

Use this copy unless a stronger verified source changes the facts:

Title:

```text
Carboplatin Injection Supply Risk Brief
```

Finding:

```text
Active shortage evidence and a supplier quality constraint create a high-risk path for hospital-ready carboplatin supply.
```

Why it matters:

```text
Carboplatin is a platinum chemotherapy medicine. Delays can force oncology teams to ration, delay, or substitute treatment, so supply teams need early warning before inventory reaches the safety threshold.
```

Action:

```text
Prepare alternate supplier order. Verify approved supplier availability and lead time before stock falls below safety threshold.
```

Caveat:

```text
API and platinum-market signals increase confidence in upstream fragility, but the direct action path is anchored in FDA and ASHP shortage evidence.
```

## Integration Plan

1. Add a report preview data object near the scenario data, or in a new file such as `src/data/carboplatin-report-preview.ts`.
2. Keep it keyed by graph node IDs so report sections can link back to the highlighted graph.
3. In `report-ready`, replace the current placeholder with a compact preview component.
4. Add buttons or affordances only if needed for the video:
   - `Open report`
   - `Export later`
   - `Back to graph`
5. Do not build PDF export, long-form report pages, authentication, persistence, or real AI report generation in this pass.

## Acceptance Criteria

- The report is readable within a few seconds.
- The top finding supports the exact graph action path.
- The visible recommendation is operational, not clinical.
- FDA and ASHP are visually treated as the strongest evidence.
- Times of India is shown as newly added supporting evidence.
- The report does not imply that South African platinum supply directly caused the U.S. shortage.
- The report does not include a patient node or patient data.
- The UI remains a placeholder/preview for the future report system, not a complete report product.
