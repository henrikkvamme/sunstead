import {
  nodeDetails,
  scriptedSourceId,
  selectedMedicineId,
} from "#/data/carboplatin-risk-scenario";

export const carboplatinDemoScenario = "carboplatin-demo";

export type SupplyRiskAgentScenario = typeof carboplatinDemoScenario;

export type ManagedInvestigationDemoResult = {
  caveat: string;
  graphUpdates: {
    actionPathUnchanged: true;
    edgesToHighlight: ["e-shortage-times-india-evidence"];
    nodesToHighlight: ["event-fda-shortage", typeof scriptedSourceId];
  };
  reportContextReady: true;
  source: {
    evidenceType: "contextual";
    id: typeof scriptedSourceId;
    publisher: "Times of India";
    relevance: string;
    title: string;
    url: string;
  };
};

export type CarboplatinDemoToolCall = {
  id: string;
  label: string;
  result: string;
  status: "complete" | "pending" | "running";
  stepId: string;
  toolName: string;
};

export type CarboplatinDemoMessage = {
  id: string;
  kind: "agent" | "source";
  text: string;
};

export type CarboplatinDemoReplayPhase = "idle" | "report-ready" | "running";

export type CarboplatinDemoReplayStep = {
  durationMs: number;
  id: string;
  label: string;
  result: string;
  revealsEvidence?: true;
  tools: Array<{
    id: string;
    input: Record<string, unknown>;
    label: string;
    result: string;
    toolName: string;
  }>;
  workingNote: string;
};

export type CarboplatinDemoReplayState = {
  addedEvidenceNodeIds: ["event-fda-shortage", typeof scriptedSourceId];
  caveat: string;
  graphUpdates: ManagedInvestigationDemoResult["graphUpdates"];
  messages: CarboplatinDemoMessage[];
  reportContextReady: boolean;
  scenario: SupplyRiskAgentScenario;
  selectedNodeId: typeof selectedMedicineId;
  source: ManagedInvestigationDemoResult["source"] & {
    mode: "scripted evidence";
  };
  toolCalls: CarboplatinDemoToolCall[];
  workingNote: string | null;
};

const timesIndiaSource = nodeDetails[scriptedSourceId]?.sources[0];

export const carboplatinDemoCaveat =
  "This source supports upstream fragility but does not prove the direct cause of the U.S. FDA shortage.";

export const carboplatinManagedInvestigationDemoResult: ManagedInvestigationDemoResult = {
  source: {
    id: scriptedSourceId,
    title:
      timesIndiaSource?.title ??
      "W Asia conflict, API shortage choke platinum-based chemo drugs' supply",
    publisher: "Times of India",
    url: timesIndiaSource?.url ?? "",
    evidenceType: "contextual",
    relevance: "Supports a 2026 upstream API-risk signal for platinum chemotherapy medicines.",
  },
  graphUpdates: {
    nodesToHighlight: ["event-fda-shortage", scriptedSourceId],
    edgesToHighlight: ["e-shortage-times-india-evidence"],
    actionPathUnchanged: true,
  },
  reportContextReady: true,
  caveat: carboplatinDemoCaveat,
};

export const carboplatinDemoReplaySteps: CarboplatinDemoReplayStep[] = [
  {
    id: "map-current-evidence",
    label: "Map current evidence",
    durationMs: 2600,
    workingNote:
      "Starting from the selected Carboplatin graph. I am reading the current shortage anchor, supplier constraint, and quality event before looking outside the mapped evidence.",
    result:
      "Mapped FDA shortage evidence, ASHP context, Accord / Intas supplier constraint, and GMP compliance event.",
    tools: [
      {
        id: "read-fda-shortage",
        toolName: "getNodeContext",
        label: "Read FDA shortage node",
        input: { nodeId: "event-fda-shortage" },
        result: "FDA shortage remains the direct evidence anchor.",
      },
      {
        id: "read-supplier",
        toolName: "getNodeContext",
        label: "Read Accord / Intas node",
        input: { nodeId: "supplier-accord-intas" },
        result: "Supplier path carries the strongest action signal.",
      },
      {
        id: "read-gmp",
        toolName: "getNodeContext",
        label: "Read GMP constraint node",
        input: { nodeId: "event-gmp" },
        result: "GMP compliance explains why supply is constrained.",
      },
    ],
  },
  {
    id: "search-newer-sources",
    label: "Search newer sources",
    durationMs: 3200,
    workingNote:
      "The mapped FDA and ASHP evidence should remain authoritative. I am searching for one newer upstream API-risk signal that supports context without creating a new clinical claim.",
    result: "Found and classified a 2026 Times of India report as contextual API-risk support.",
    tools: [
      {
        id: "search-api-risk",
        toolName: "webSearch",
        label: "Search 2026 API-risk signal",
        input: {
          query: "2026 platinum chemotherapy API shortage carboplatin source",
          maxResults: 3,
        },
        result: "Matched a 2026 platinum chemotherapy API shortage report.",
      },
      {
        id: "fetch-times-india",
        toolName: "webFetch",
        label: "Fetch Times of India article",
        input: { url: carboplatinManagedInvestigationDemoResult.source.url },
        result: "Fetched article metadata and source URL.",
      },
      {
        id: "classify-source",
        toolName: "classifySource",
        label: "Classify evidence strength",
        input: { sourceId: scriptedSourceId, expectedRole: "contextual API-risk support" },
        result: "Classified as contextual amplification, not direct shortage causation.",
      },
    ],
  },
  {
    id: "update-graph",
    label: "Update graph",
    durationMs: 2700,
    workingNote:
      "This is the graph mutation point. I will add the article as a supporting Evidence Satellite, not as a new red action path.",
    result:
      "Inserted and connected source-times-india-2026 as contextual evidence on the FDA shortage node.",
    revealsEvidence: true,
    tools: [
      {
        id: "insert-times-india-node",
        toolName: "insertGraphEvidenceNode",
        label: "Insert source node",
        input: {
          nodeId: scriptedSourceId,
          evidenceType: "contextual",
          url: carboplatinManagedInvestigationDemoResult.source.url,
        },
        result: "Inserted Times of India report as source-times-india-2026.",
      },
      {
        id: "connect-api-source",
        toolName: "connectGraphEvidence",
        label: "Connect source to API risk",
        input: {
          edgeIds: ["e-shortage-times-india-evidence"],
          sourceId: scriptedSourceId,
          targetId: "event-fda-shortage",
        },
        result: "Connected the source as contextual evidence on FDA current shortage.",
      },
      {
        id: "highlight-delta",
        toolName: "highlightGraphDelta",
        label: "Highlight graph delta",
        input: carboplatinManagedInvestigationDemoResult.graphUpdates,
        result: "Highlighted the new source and API-risk connector.",
      },
    ],
  },
  {
    id: "prepare-report",
    label: "Prepare report context",
    durationMs: 2400,
    workingNote:
      "The report can now combine direct evidence, supplier constraint, upstream caveat, and the recommended operational action.",
    result: "Report context prepared with evidence, risk path, caveat, and recommended action.",
    tools: [
      {
        id: "prepare-report-context",
        toolName: "prepareReportContext",
        label: "Prepare report context",
        input: { reportId: "report-carboplatin-demo", includeCaveat: true },
        result: "Prepared report context from mapped and newly inserted evidence.",
      },
      {
        id: "validate-action-path",
        toolName: "validateActionPathUnchanged",
        label: "Validate action path",
        input: {
          expectedActionPath:
            "Carboplatin Injection -> Accord / Intas -> GMP compliance constraint",
        },
        result: "Action path remains unchanged after adding contextual source.",
      },
    ],
  },
];

export function buildCarboplatinDemoStreamingSystemPrompt() {
  return [
    "You are Sanitas Graph Operator running the deterministic carboplatin-demo scenario.",
    "Stream concise progress summaries between tool groups. These summaries are user-visible status text, not hidden chain-of-thought.",
    "First gather mapped graph context, then search for one newer supporting upstream API-risk source.",
    "When a suitable newer source is found, call the graph insertion tool before connecting and highlighting it.",
    "Keep FDA and ASHP as direct evidence anchors. Treat Times of India as contextual amplification only.",
    "Do not create patient models, patient-level predictions, or clinical treatment advice.",
    "End with: Report context prepared: evidence, risk path, and recommended action are ready.",
  ].join("\n");
}

const demoMessages: CarboplatinDemoMessage[] = [
  {
    id: "fda-anchor",
    kind: "agent",
    text: "I found the hard evidence anchor: FDA lists Carboplatin Injection in shortage.",
  },
  {
    id: "supplier-constraint",
    kind: "agent",
    text: "The clearest supplier constraint is Accord / Intas, tied to GMP compliance requirements.",
  },
  {
    id: "api-check",
    kind: "source",
    text: "I am checking whether newer upstream evidence changes the risk picture.",
  },
  {
    id: "supporting-source",
    kind: "source",
    text: "I found one supporting 2026 API-risk source. It strengthens context but does not change the action path.",
  },
  {
    id: "report-ready",
    kind: "agent",
    text: "Report context prepared: evidence, risk path, and recommended action are ready.",
  },
];

export function isSupplyRiskAgentScenario(
  scenario: string | undefined,
): scenario is SupplyRiskAgentScenario {
  return scenario === carboplatinDemoScenario;
}

export function normalizeCarboplatinManagedInvestigationResult(
  _rawResult: unknown,
): ManagedInvestigationDemoResult {
  return carboplatinManagedInvestigationDemoResult;
}

export function getCarboplatinDemoReplayState(
  phase: CarboplatinDemoReplayPhase = "running",
  currentStepIndex = 0,
  workingNote?: string,
): CarboplatinDemoReplayState {
  const reportContextReady = phase === "report-ready";
  const activeStep = phase === "running" ? carboplatinDemoReplaySteps[currentStepIndex] : undefined;

  return {
    scenario: carboplatinDemoScenario,
    selectedNodeId: selectedMedicineId,
    toolCalls: carboplatinDemoReplaySteps.flatMap((step, stepIndex) =>
      step.tools.map((tool) => ({
        id: tool.id,
        label: tool.label,
        result: tool.result,
        status: statusForToolCall(phase, currentStepIndex, stepIndex),
        stepId: step.id,
        toolName: tool.toolName,
      })),
    ),
    messages: reportContextReady
      ? demoMessages
      : carboplatinDemoReplaySteps.slice(0, Math.max(0, currentStepIndex)).map((step) => ({
          id: `${step.id}-result`,
          kind: step.tools.some(
            (tool) => tool.toolName === "webSearch" || tool.toolName === "webFetch",
          )
            ? "source"
            : "agent",
          text: step.result,
        })),
    addedEvidenceNodeIds: ["event-fda-shortage", scriptedSourceId],
    graphUpdates: carboplatinManagedInvestigationDemoResult.graphUpdates,
    source: {
      ...carboplatinManagedInvestigationDemoResult.source,
      mode: "scripted evidence",
    },
    caveat: carboplatinDemoCaveat,
    reportContextReady,
    workingNote: activeStep ? (workingNote ?? activeStep.workingNote) : null,
  };
}

function statusForToolCall(
  phase: CarboplatinDemoReplayPhase,
  currentStepIndex: number,
  index: number,
): CarboplatinDemoToolCall["status"] {
  if (phase === "report-ready") {
    return "complete";
  }

  if (phase === "idle") {
    return "pending";
  }

  if (index < currentStepIndex) {
    return "complete";
  }

  if (index === currentStepIndex) {
    return "running";
  }

  return "pending";
}
