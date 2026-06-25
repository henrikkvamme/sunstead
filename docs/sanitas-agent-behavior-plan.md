# Sanitas Agent Behavior Plan

## Purpose

Define how the Sanitas AI layer should behave in the Cisplatin Injection demo. The demo must feel agentic, but the judged path should be heavily scripted so the story is clear, fast, and repeatable.

The agent should not discover the main shortage story live. The graph already knows the important path:

```text
Cisplatin Injection -> FDA current shortage -> Accord / Intas -> GMP compliance constraint
```

The agent's job in the demo is to explain, verify, add one supporting evidence source, and prepare report context.

## Demo Principle

The video only gives the viewer a few seconds to understand the AI behavior. Optimize for legibility, not autonomy.

The agent should visibly do five things:

1. Read the selected graph node.
2. Inspect mapped evidence.
3. Confirm the single action path.
4. Add one supporting evidence source.
5. End with report-ready context.

It should not branch into a long research session, create many new nodes, or debate clinical alternatives.

## Agent Roles

### 1. Sanitas Operator Agent

Current implementation target: `src/ai/supply-risk-agent.ts`.

This is the user-facing agent. It owns the chat stream, tool-call list, short explanations, and final handoff to the report-ready state.

Responsibilities:

- Keep the conversation operational and concise.
- Call local supply graph tools before making claims.
- Present the highest-risk path first.
- Separate evidence from inference.
- Trigger managed source investigation only when the user clicks `Investigate`.
- Translate managed-agent output into graph/report-ready UI state.

This agent should be deterministic in the demo path. It can use the LLM for wording, but the steps and final outcome should be constrained.

### 2. Managed Source Investigator

Current implementation target: `src/ai/claude-managed-agent.ts`.

This is the external research worker. It should be used as a specialist sub-agent for public-source investigation, not as the main demo narrator.

Responsibilities:

- Search/fetch external sources.
- Avoid duplicating existing FDA/ASHP sources.
- Return concise source candidates with relevance and confidence.
- Propose graph additions, but never directly mutate the graph in the demo.

For the demo, the managed investigator should always converge on:

```text
Times of India API report -> 2026 API shortage signal -> Platinum-based API context
```

This is supporting evidence only. It must not become a second urgent action path.

### 3. Report Context Agent

This can start as a logical role inside the operator agent. It does not need a separate runtime agent yet.

Responsibilities:

- Convert mapped graph evidence into report-ready state.
- Preserve the same single action path.
- Keep caveats visible:
  - patient impact is narration only;
  - API/platinum signals are risk amplifiers;
  - FDA/ASHP are the direct shortage evidence.

Do not build full report generation here. The current UI should only show that report context is ready.

## Tool Strategy

Use a small number of visible tool calls. The viewer should understand the sequence instantly.

Required scripted tool-call sequence:

```text
Inspect FDA shortage evidence
Check supplier-level constraints
Search newer API-risk sources
Add supporting evidence
Prepare report context
```

Suggested real/internal tool mapping:

| Visible tool call                  | Local behavior                                                                        | Managed-agent behavior  |
| ---------------------------------- | ------------------------------------------------------------------------------------- | ----------------------- |
| `Inspect FDA shortage evidence`    | `getNodeContext(event-fda-shortage)`                                                  | none                    |
| `Check supplier-level constraints` | `getNodeContext(supplier-accord-intas)` and `getNodeContext(event-gmp)`               | none                    |
| `Search newer API-risk sources`    | start managed investigation for `component-platinum-api` or `event-api-shortage-2026` | web search/fetch        |
| `Add supporting evidence`          | add/highlight `source-times-india-2026` and `event-api-shortage-2026`                 | return source candidate |
| `Prepare report context`           | move UI to `report-ready`                                                             | none                    |

Do not expose every internal tool call. The UI should show a curated replay, not a raw debug log.

## State Flow

The frontend state machine should stay aligned with this sequence:

```text
overview
  -> click Cisplatin Injection
medicine-focus
  -> click FDA current shortage or GMP compliance constraint
node-detail
  -> click Investigate
investigating
  -> scripted replay finishes
report-ready
```

The managed agent may run in parallel, but the demo must have a deterministic fallback. If managed agents are not configured, the UI should still run the scripted replay and mark the source as `scripted evidence`.

## Heavily Scripted System Prompt

Use this as the base system prompt for the operator-facing Sanitas agent during the demo.

```text
You are the Sanitas supply-risk investigation agent for a live product demo.

Your behavior is intentionally scripted for clarity. You are investigating one medicine:
Cisplatin Injection.

The primary action path is fixed:
Cisplatin Injection -> FDA current shortage -> Accord / Intas -> GMP compliance constraint.

Your goals:
1. Explain the selected node in operational supply-risk language.
2. Confirm the mapped evidence behind the action path.
3. Use tools before making factual claims about medicines, suppliers, events, sites, or sources.
4. Add at most one new supporting evidence source during the demo.
5. End by preparing report context, not by writing a full report.

Important evidence hierarchy:
- FDA Cisplatin Injection shortage page is the primary direct evidence.
- ASHP Cisplatin shortage page is the clinical pharmacy evidence.
- Times of India May 2026 API shortage reporting is supporting upstream evidence.
- Axios, NCCN/Health, Guardian, Economic Times, and WPIC are context only.

Strict narrative constraints:
- Keep only one action path urgent.
- Do not make API shortage, platinum supply, South Africa, demand increase, shipping delay, or discontinued presentations into separate red paths.
- Treat API and platinum signals as risk amplifiers, not the direct proven cause of the U.S. shortage.
- Do not model patients or patient-specific care.
- Do not provide clinical treatment advice.
- Do not recommend automatic procurement or treatment decisions.
- Do not claim the graph is complete; say it is mapped evidence plus current investigation.

Output style:
- Short, operational, confident.
- Prefer 1-3 sentence messages.
- Always distinguish "evidence" from "inference".
- Use source titles returned by tools when citing evidence.
- Avoid long research summaries unless the user explicitly asks.

Demo completion behavior:
When the investigation finishes, say:
"Report context prepared: evidence, risk path, and recommended action are ready."

The recommended action is:
"Prepare alternate supplier order. Verify approved supplier availability and lead time before stock falls below safety threshold."
```

## Managed Investigator Prompt

Use this as the managed-agent task prompt for the demo path.

```text
You are a managed external-source investigator for Sanitas.

Investigate public sources related to Cisplatin Injection supply risk.

The main path is already mapped:
Cisplatin Injection -> FDA current shortage -> Accord / Intas -> GMP compliance constraint.

Do not rediscover or replace the main path. Find one newer supporting source that helps explain upstream risk without creating a second urgent path.

Preferred target:
- A 2026 source about platinum-based chemotherapy API shortage or API/raw-material pressure.

Existing direct sources:
- FDA Cisplatin Injection shortage page.
- ASHP Cisplatin Injection shortage page.

Return only:
1. One recommended source with title, URL, publisher, date if available, and relevance.
2. Whether it is primary/direct/contextual.
3. One proposed event node if needed.
4. One proposed edge from the new source to the relevant graph context.
5. One caveat that prevents overclaiming.

Do not provide clinical treatment advice.
Do not add patient data.
Do not propose more than one new source for the demo path.
```

## Expected Managed-Agent Output

For the scripted demo, normalize managed-agent output into this shape:

```ts
type ManagedInvestigationDemoResult = {
  source: {
    id: "source-times-india-2026";
    title: "W Asia conflict, API shortage choke platinum-based chemo drugs' supply";
    publisher: "Times of India";
    url: string;
    evidenceType: "contextual";
    relevance: "Supports a 2026 upstream API-risk signal for platinum chemotherapy medicines.";
  };
  graphUpdates: {
    nodesToHighlight: ["event-api-shortage-2026", "source-times-india-2026"];
    edgesToHighlight: ["e-api-shortage-signal", "e-api-shortage-times-india"];
    actionPathUnchanged: true;
  };
  reportContextReady: true;
  caveat: "This source supports upstream fragility but does not prove the direct cause of the U.S. FDA shortage.";
};
```

## UI Behavior During Agent Replay

The chat panel should feel active but not verbose.

Suggested visible messages:

```text
I found the hard evidence anchor: FDA lists Cisplatin Injection in shortage.
The clearest supplier constraint is Accord / Intas, tied to GMP compliance requirements.
I am checking whether newer upstream evidence changes the risk picture.
I found one supporting 2026 API-risk source. It strengthens context but does not change the action path.
Report context prepared: evidence, risk path, and recommended action are ready.
```

Graph behavior:

- Pulse the existing action path first.
- Add/highlight `Times of India API report` as a supporting source.
- Keep the new source visually less urgent than the action path.
- Move to `report-ready`.

## Failure And Fallback Behavior

The demo should not fail if managed agents are unavailable.

If missing managed-agent config:

- Continue scripted replay locally.
- Show a subtle internal status: `Managed source investigator unavailable; using prepared demo evidence.`
- Still add/highlight `source-times-india-2026`.
- Still end in `report-ready`.

If managed agent returns too many sources:

- Select only the best 2026 API-risk source.
- Store the rest as hidden candidates or ignore them for the demo.
- Do not add multiple new evidence nodes during the video.

If managed agent returns contradictory or weak evidence:

- Do not change the main risk path.
- Say: `No stronger source changed the action path; report context remains anchored in FDA and ASHP evidence.`
- End in `report-ready`.

## Implementation Steps

1. Update `buildSupplyRiskAgentInstructions` in `src/ai/prompts.ts` to support a `demoMode` or `scriptedScenario` option.
2. Keep the current general-purpose prompt for non-demo use.
3. Add a `buildCarboplatinDemoAgentInstructions` helper that uses the scripted system prompt above.
4. Make `createSupplyRiskAgent` accept `scenario?: "carboplatin-demo"`.
5. In demo mode, lower temperature to `0` or `0.1` and cap steps tightly.
6. Keep `startManagedSourceInvestigation` as a tool, but wrap its result with deterministic normalization.
7. Add a frontend adapter that maps agent events into:
   - visible tool call rows;
   - graph node highlights;
   - `addedEvidence`;
   - `report-ready`.
8. Add tests for:
   - scripted prompt includes the fixed action path;
   - managed-agent prompt asks for only one new source;
   - fallback path still ends report-ready;
   - API/platinum caveat is present;
   - patient data and clinical advice are forbidden.

## Acceptance Criteria

- The agent always starts from the selected graph node.
- The demo path always ends in report-ready.
- Only one new source is visibly added.
- The main action path remains unchanged.
- FDA/ASHP remain the direct evidence anchors.
- Managed-agent failure does not break the demo.
- The system prompt explicitly forbids patient modeling and clinical treatment advice.
- The visible chat can be understood in a few seconds.
