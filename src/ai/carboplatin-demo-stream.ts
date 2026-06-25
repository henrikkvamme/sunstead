import { createUIMessageStream, createUIMessageStreamResponse, type UIMessage } from "ai";

import { graphNodes, nodeDetails, scriptedSourceId } from "#/data/carboplatin-risk-scenario";

import {
  buildCarboplatinDemoStreamingSystemPrompt,
  carboplatinDemoCaveat,
  carboplatinDemoReplaySteps,
  carboplatinManagedInvestigationDemoResult,
  getCarboplatinDemoReplayState,
  type CarboplatinDemoReplayStep,
} from "./carboplatin-demo";
import { getSupplyGraphNodeContext } from "./supply-graph";

type DemoStepStatus = "complete" | "pending" | "running";

type CarboplatinDemoStreamData = {
  "agent-reasoning": {
    afterToolId?: string;
    beforeToolId?: string;
    id: string;
    status: "complete" | "streaming";
    stepId: string;
    text: string;
  };
  "agent-step": {
    id: string;
    label: string;
    status: DemoStepStatus;
    summary?: string;
    toolCount: number;
  };
  "agent-tool": {
    id: string;
    label: string;
    outputSummary?: string;
    status: DemoStepStatus;
    stepId: string;
    toolName: string;
  };
  "graph-update": {
    addedEvidenceNodeIds: string[];
    edgesToHighlight: string[];
    nodesToHighlight: string[];
    source: typeof carboplatinManagedInvestigationDemoResult.source;
  };
  "report-ready": {
    caveat: string;
    reportContextReady: true;
    sentence: string;
  };
};

type CarboplatinDemoUIMessage = UIMessage<unknown, CarboplatinDemoStreamData>;
type CarboplatinDemoStreamWriter = Parameters<
  Parameters<typeof createUIMessageStream<CarboplatinDemoUIMessage>>[0]["execute"]
>[0]["writer"];

export type CreateCarboplatinDemoStreamResponseOptions = {
  abortSignal?: AbortSignal;
  timing?: {
    reasoningDelayMs?: number;
    toolDelayMs?: number;
  };
};

const finalReportReadySentence =
  "Report context prepared: evidence, risk path, and recommended action are ready.";

export function createCarboplatinDemoStreamResponse(
  options: CreateCarboplatinDemoStreamResponseOptions = {},
) {
  const stream = createUIMessageStream<CarboplatinDemoUIMessage>({
    execute: async ({ writer }) => {
      writer.write({ type: "start", messageId: "carboplatin-demo-message" });
      writer.write({
        type: "text-start",
        id: "carboplatin-demo-script",
      });
      writer.write({
        type: "text-delta",
        id: "carboplatin-demo-script",
        delta: buildCarboplatinDemoStreamingSystemPrompt(),
      });
      writer.write({ type: "text-end", id: "carboplatin-demo-script" });

      for (const step of carboplatinDemoReplaySteps) {
        throwIfAborted(options.abortSignal);
        await runDemoStep(writer, step, options);
      }

      writer.write({
        type: "data-report-ready",
        id: "carboplatin-demo-report-ready",
        data: {
          caveat: carboplatinDemoCaveat,
          reportContextReady: true,
          sentence: finalReportReadySentence,
        },
      });
      writer.write({
        type: "text-start",
        id: "carboplatin-demo-final",
      });
      writer.write({
        type: "text-delta",
        id: "carboplatin-demo-final",
        delta: finalReportReadySentence,
      });
      writer.write({ type: "text-end", id: "carboplatin-demo-final" });
      writer.write({ type: "finish", finishReason: "stop" });
    },
    onError: (error) => (error instanceof Error ? error.message : "Demo agent stream failed."),
  });

  return createUIMessageStreamResponse({ stream });
}

async function runDemoStep(
  writer: CarboplatinDemoStreamWriter,
  step: CarboplatinDemoReplayStep,
  options: CreateCarboplatinDemoStreamResponseOptions,
) {
  writer.write({ type: "start-step" });
  writer.write({
    type: "data-agent-step",
    id: step.id,
    data: {
      id: step.id,
      label: step.label,
      status: "running",
      toolCount: step.tools.length,
    },
  });

  for (const tool of step.tools) {
    throwIfAborted(options.abortSignal);
    await streamReasoningSummary(
      writer,
      step.id,
      `${tool.id}-before`,
      reasoningBeforeTool(tool.id),
      options,
      { beforeToolId: tool.id },
    );

    writer.write({
      type: "data-agent-tool",
      id: tool.id,
      data: {
        id: tool.id,
        label: tool.label,
        status: "running",
        stepId: step.id,
        toolName: tool.toolName,
      },
    });
    writer.write({
      type: "tool-input-start",
      toolCallId: tool.id,
      toolName: tool.toolName,
      title: tool.label,
    });
    writer.write({
      type: "tool-input-available",
      toolCallId: tool.id,
      toolName: tool.toolName,
      input: tool.input,
      title: tool.label,
    });

    await delay(toolDelayFor(tool.toolName, options), options.abortSignal);
    const output = executeDemoTool(tool.toolName, tool.input);

    writer.write({
      type: "tool-output-available",
      toolCallId: tool.id,
      output,
    });
    writer.write({
      type: "data-agent-tool",
      id: tool.id,
      data: {
        id: tool.id,
        label: tool.label,
        outputSummary: tool.result,
        status: "complete",
        stepId: step.id,
        toolName: tool.toolName,
      },
    });

    if (tool.toolName === "insertGraphEvidenceNode") {
      writeGraphEvidenceUpdate(writer);
    }

    await streamReasoningSummary(
      writer,
      step.id,
      `${tool.id}-after`,
      reasoningAfterTool(tool.id),
      options,
      { afterToolId: tool.id },
    );
  }

  writer.write({
    type: "data-agent-step",
    id: step.id,
    data: {
      id: step.id,
      label: step.label,
      status: "complete",
      summary: step.result,
      toolCount: step.tools.length,
    },
  });
  writer.write({ type: "finish-step" });
}

async function streamReasoningSummary(
  writer: CarboplatinDemoStreamWriter,
  stepId: string,
  id: string,
  textToStream: string,
  options: CreateCarboplatinDemoStreamResponseOptions,
  placement: { afterToolId?: string; beforeToolId?: string },
) {
  const chunks = textToStream.match(/.{1,12}(?:\s|$)/g) ?? [textToStream];
  let text = "";

  for (const chunk of chunks) {
    throwIfAborted(options.abortSignal);
    text += chunk;
    writer.write({
      type: "data-agent-reasoning",
      id,
      data: {
        ...placement,
        id,
        status: "streaming",
        stepId,
        text,
      },
    });
    await delay(options.timing?.reasoningDelayMs ?? 24, options.abortSignal);
  }

  writer.write({
    type: "data-agent-reasoning",
    id,
    data: {
      ...placement,
      id,
      status: "complete",
      stepId,
      text: textToStream,
    },
  });
}

function writeGraphEvidenceUpdate(writer: CarboplatinDemoStreamWriter) {
  writer.write({
    type: "source-url",
    sourceId: scriptedSourceId,
    title: carboplatinManagedInvestigationDemoResult.source.title,
    url: carboplatinManagedInvestigationDemoResult.source.url,
  });
  writer.write({
    type: "data-graph-update",
    id: "carboplatin-demo-graph-update",
    data: {
      addedEvidenceNodeIds: getCarboplatinDemoReplayState("report-ready").addedEvidenceNodeIds,
      edgesToHighlight: carboplatinManagedInvestigationDemoResult.graphUpdates.edgesToHighlight,
      nodesToHighlight: carboplatinManagedInvestigationDemoResult.graphUpdates.nodesToHighlight,
      source: carboplatinManagedInvestigationDemoResult.source,
    },
  });
}

function reasoningBeforeTool(toolId: string) {
  const summaries: Record<string, string> = {
    "read-fda-shortage":
      "First I need the official shortage anchor. If this node is weak, no newer article should drive the action path.",
    "read-supplier":
      "The next check is supplier-specific, because the operational recommendation needs a constrained supplier path.",
    "read-gmp":
      "I am checking whether the supplier constraint has a concrete quality or compliance explanation.",
    "search-api-risk":
      "The mapped evidence is enough for the shortage path, so the web search is deliberately narrow: one newer API-risk signal only.",
    "fetch-times-india":
      "The search found a candidate source. I need the article URL and publisher context before it can enter the graph.",
    "classify-source":
      "Before mutating the graph, I am classifying the source strength so it cannot overclaim causation.",
    "insert-times-india-node":
      "The source is useful as evidence, so the next operation is a graph insertion rather than a report-only note.",
    "connect-api-source":
      "Now the inserted article needs a bounded evidence edge to FDA current shortage, without claiming it caused the shortage.",
    "highlight-delta":
      "I am highlighting the new evidence satellite and its FDA shortage evidence edge so the action path remains stable.",
    "prepare-report-context":
      "The graph has enough context for the report handoff: direct evidence, supplier constraint, supporting source, and caveat.",
    "validate-action-path":
      "The final check is that the new article did not create a second urgent path or change the recommended operational action.",
  };

  return summaries[toolId] ?? "I am choosing the next tool based on the current graph state.";
}

function reasoningAfterTool(toolId: string) {
  const summaries: Record<string, string> = {
    "read-fda-shortage":
      "FDA remains the hard evidence anchor, so later sources can support context but cannot replace this shortage signal.",
    "read-supplier":
      "Accord / Intas keeps the path operational: the question is supplier readiness, not patient-level impact.",
    "read-gmp":
      "The compliance event gives the supplier path a concrete constraint, which is enough to search for upstream amplification.",
    "search-api-risk":
      "The result set points to a 2026 platinum chemotherapy API shortage report, matching the narrow search target.",
    "fetch-times-india":
      "The fetched article is suitable as a visible source node because it has a stable publisher, title, and article URL.",
    "classify-source":
      "The source is contextual only. It strengthens upstream fragility without proving the direct cause of the U.S. shortage.",
    "insert-times-india-node":
      "The new source node can now be clicked in the graph and opened as the article the agent found.",
    "connect-api-source":
      "The edge placement makes the article visible as contextual evidence under FDA current shortage while preserving FDA/ASHP as direct anchors.",
    "highlight-delta":
      "The highlighted delta is intentionally small: source-times-india-2026 and its FDA shortage evidence edge only.",
    "prepare-report-context":
      "The report context is ready to explain evidence, risk path, caveat, and the recommended supplier-readiness action.",
    "validate-action-path":
      "The action path is unchanged, so the demo ends with a report-ready state instead of another search branch.",
  };

  return summaries[toolId] ?? "The tool result supports the next graph operation.";
}

function executeDemoTool(toolName: string, input: Record<string, unknown>) {
  if (toolName === "getNodeContext") {
    const nodeId = typeof input.nodeId === "string" ? input.nodeId : "";

    return getSupplyGraphNodeContext(nodeId);
  }

  if (toolName === "webSearch") {
    return {
      query: input.query,
      results: [
        {
          id: scriptedSourceId,
          publisher: carboplatinManagedInvestigationDemoResult.source.publisher,
          title: carboplatinManagedInvestigationDemoResult.source.title,
          url: carboplatinManagedInvestigationDemoResult.source.url,
        },
      ],
    };
  }

  if (toolName === "webFetch") {
    const source = nodeDetails[scriptedSourceId]?.sources[0];

    return {
      fetched: true,
      publisher: carboplatinManagedInvestigationDemoResult.source.publisher,
      title: source?.title ?? carboplatinManagedInvestigationDemoResult.source.title,
      url: source?.url ?? carboplatinManagedInvestigationDemoResult.source.url,
    };
  }

  if (toolName === "classifySource") {
    return {
      caveat: carboplatinDemoCaveat,
      evidenceType: "contextual",
      sourceId: scriptedSourceId,
      supports: "upstream platinum chemotherapy API risk",
    };
  }

  if (toolName === "insertGraphEvidenceNode") {
    return {
      inserted: true,
      node: graphNodes.find((node) => node.id === scriptedSourceId),
      source: carboplatinManagedInvestigationDemoResult.source,
    };
  }

  if (toolName === "connectGraphEvidence") {
    return {
      connected: true,
      edges: carboplatinManagedInvestigationDemoResult.graphUpdates.edgesToHighlight,
      sourceId: scriptedSourceId,
      targetId: "event-fda-shortage",
    };
  }

  if (toolName === "highlightGraphDelta") {
    return carboplatinManagedInvestigationDemoResult.graphUpdates;
  }

  if (toolName === "prepareReportContext") {
    return getCarboplatinDemoReplayState("report-ready");
  }

  if (toolName === "validateActionPathUnchanged") {
    return {
      actionPathUnchanged: true,
      caveat: carboplatinDemoCaveat,
      reportContextReady: true,
    };
  }

  return { ok: true };
}

function toolDelayFor(toolName: string, options: CreateCarboplatinDemoStreamResponseOptions) {
  if (typeof options.timing?.toolDelayMs === "number") {
    return options.timing.toolDelayMs;
  }

  const delaysByToolName: Record<string, number> = {
    classifySource: 850,
    connectGraphEvidence: 880,
    getNodeContext: 720,
    highlightGraphDelta: 650,
    insertGraphEvidenceNode: 940,
    prepareReportContext: 820,
    validateActionPathUnchanged: 680,
    webFetch: 1100,
    webSearch: 1250,
  };

  return delaysByToolName[toolName] ?? 760;
}

async function delay(ms: number, abortSignal?: AbortSignal) {
  if (ms <= 0) {
    return;
  }

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(resolve, ms);

    abortSignal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timeout);
        reject(new DOMException("The request was aborted.", "AbortError"));
      },
      { once: true },
    );
  });
}

function throwIfAborted(abortSignal?: AbortSignal) {
  if (abortSignal?.aborted) {
    throw new DOMException("The request was aborted.", "AbortError");
  }
}
