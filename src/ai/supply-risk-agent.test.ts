import { describe, expect, it } from "vite-plus/test";

import { agentRequestSchema } from "#/routes/api/agent";

import {
  buildCarboplatinDemoAgentInstructions,
  buildCarboplatinDemoStreamingSystemPrompt,
  buildCarboplatinManagedInvestigationPrompt,
  buildNodeInvestigationPrompt,
  buildSupplyRiskAgentInstructions,
  carboplatinDemoScenario,
  carboplatinDemoReplaySteps,
  ClaudeManagedAgentClient,
  createCarboplatinDemoStreamResponse,
  createSupplyRiskAnthropicModel,
  claudeManagedAgentsBetaHeader,
  createSupplyRiskAgent,
  defaultSupplyRiskAgentModel,
  getCarboplatinDemoReplayState,
  getSupplyGraphNodeContext,
  getSupplyRiskAgentModelId,
  listPrioritySupplyRisks,
  normalizeCarboplatinManagedInvestigationResult,
  resolveClaudeManagedAgentConfig,
  searchSupplyGraph,
  startClaudeManagedSourceInvestigation,
  supplyRiskAgentId,
} from "./index";

describe("supply risk agent module", () => {
  it("searches the supply graph with risk and kind filters", () => {
    const results = searchSupplyGraph({
      kinds: ["supplier"],
      query: "intas",
      riskLevels: ["critical"],
    });

    expect(results).toEqual([
      expect.objectContaining({
        id: "supplier-accord-intas",
        kind: "supplier",
        risk: "critical",
      }),
    ]);
  });

  it("returns detailed node context for tool use", () => {
    const context = getSupplyGraphNodeContext("event-fda-shortage");

    expect(context.found).toBe(true);
    if (!context.found) {
      throw new Error("Expected event-fda-shortage to be present");
    }

    expect(context.node.risk).toBe("critical");
    expect(context.details?.sources.length).toBeGreaterThan(0);
  });

  it("returns priority risks before stable nodes", () => {
    const risks = listPrioritySupplyRisks(3);

    expect(risks).toHaveLength(3);
    expect(risks.every((risk) => risk.risk !== "stable")).toBe(true);
    expect(risks[0]?.risk).toBe("critical");
  });

  it("builds a reusable ToolLoopAgent without calling a provider", () => {
    const agent = createSupplyRiskAgent({
      maxSteps: 3,
      today: new Date("2026-06-25T00:00:00.000Z"),
    });

    expect(agent.id).toBe(supplyRiskAgentId);
    expect(Object.keys(agent.tools).sort()).toEqual([
      "getNodeContext",
      "listPriorityRisks",
      "searchSupplyGraph",
      "startManagedSourceInvestigation",
    ]);
  });

  it("uses the configured model id fallback", () => {
    expect(getSupplyRiskAgentModelId(undefined)).toBe(defaultSupplyRiskAgentModel);
    expect(getSupplyRiskAgentModelId("anthropic/claude-sonnet-4.6")).toBe("claude-sonnet-4-6");
    expect(getSupplyRiskAgentModelId("claude-opus-4-8")).toBe("claude-opus-4-8");
  });

  it("creates the operator model with the Anthropic provider", () => {
    const model = createSupplyRiskAnthropicModel("claude-sonnet-4-6", {
      ANTHROPIC_API_KEY: "test-key",
      ANTHROPIC_BASE_URL: "https://api.anthropic.test/v1",
    });

    expect(model.provider).toBe("anthropic.messages");
    expect(model.modelId).toBe("claude-sonnet-4-6");
  });

  it("keeps instructions grounded in agent behavior", () => {
    const instructions = buildSupplyRiskAgentInstructions(new Date("2026-06-25T00:00:00.000Z"));

    expect(instructions).toContain("Today is 2026-06-25");
    expect(instructions).toContain("Use the supply graph tools");
    expect(instructions).toContain("delegate live external source investigation");
    expect(instructions).toContain("never provide clinical treatment advice");
  });

  it("builds scripted Carboplatin demo operator instructions", () => {
    const instructions = buildCarboplatinDemoAgentInstructions(
      new Date("2026-06-25T00:00:00.000Z"),
    );

    expect(instructions).toContain(
      "Carboplatin Injection -> FDA current shortage -> Accord / Intas -> GMP compliance constraint",
    );
    expect(instructions).toContain(
      "Report context prepared: evidence, risk path, and recommended action are ready.",
    );
    expect(instructions).toContain("Do not model patients or patient-specific care.");
    expect(instructions).toContain("Do not provide clinical treatment advice.");
  });

  it("builds streamed demo status instructions without exposing private reasoning", () => {
    const instructions = buildCarboplatinDemoStreamingSystemPrompt();

    expect(instructions).toContain("deterministic carboplatin-demo scenario");
    expect(instructions).toContain("Stream concise progress summaries between tool groups");
    expect(instructions).toContain("not hidden chain-of-thought");
    expect(instructions).toContain(
      "When a suitable newer source is found, call the graph insertion tool",
    );
    expect(instructions).toContain(
      "Report context prepared: evidence, risk path, and recommended action are ready.",
    );
  });

  it("uses scripted demo instructions through the general instruction builder", () => {
    const instructions = buildSupplyRiskAgentInstructions(new Date("2026-06-25T00:00:00.000Z"), {
      scenario: carboplatinDemoScenario,
    });

    expect(instructions).toContain("Your behavior is intentionally scripted for clarity");
    expect(instructions).toContain("Prepare alternate supplier order");
  });

  it("builds selected-node investigation prompts for live source discovery", () => {
    const prompt = buildNodeInvestigationPrompt({
      maxSources: 5,
      nodeId: "supplier-accord-intas",
      question: "Find newer regulatory sources.",
    });

    expect(prompt).toContain("supplier-accord-intas");
    expect(prompt).toContain("Find newer regulatory sources.");
    expect(prompt).toContain("Proposed graph nodes");
    expect(prompt).toContain("actionable operator plan");
  });

  it("builds a narrow managed-agent prompt for the Carboplatin demo path", () => {
    const prompt = buildCarboplatinManagedInvestigationPrompt({
      nodeId: "event-api-shortage-2026",
    });

    expect(prompt).toContain("Find one newer supporting source");
    expect(prompt).toContain("A 2026 source about platinum-based chemotherapy API shortage");
    expect(prompt).toContain("Do not propose more than one new source for the demo path.");
    expect(prompt).toContain("Do not provide clinical treatment advice.");
  });

  it("normalizes managed-agent output to the deterministic demo evidence result", () => {
    for (const rawResult of [
      { configured: false, status: "not_configured" },
      { sources: [{ title: "Unrelated weak evidence" }] },
      { sources: [{ title: "A source" }, { title: "Another source" }] },
    ]) {
      const result = normalizeCarboplatinManagedInvestigationResult(rawResult);

      expect(result.source.id).toBe("source-times-india-2026");
      expect(result.source.publisher).toBe("Times of India");
      expect(result.graphUpdates.nodesToHighlight).toEqual([
        "event-fda-shortage",
        "source-times-india-2026",
      ]);
      expect(result.graphUpdates.edgesToHighlight).toEqual(["e-shortage-times-india-evidence"]);
      expect(result.graphUpdates.actionPathUnchanged).toBe(true);
      expect(result.reportContextReady).toBe(true);
      expect(result.caveat).toContain("does not prove the direct cause");
    }
  });

  it("returns replay state for visible demo tool calls and report-ready fallback", () => {
    const running = getCarboplatinDemoReplayState("running", 1, "Searching newer evidence");
    const inserting = getCarboplatinDemoReplayState("running", 2);
    const reportReady = getCarboplatinDemoReplayState("report-ready");

    expect(
      carboplatinDemoReplaySteps.some((step) =>
        step.tools.some((tool) => tool.toolName === "webSearch"),
      ),
    ).toBe(true);
    expect(
      carboplatinDemoReplaySteps.some((step) =>
        step.tools.some((tool) => tool.toolName === "webFetch"),
      ),
    ).toBe(true);
    expect(
      carboplatinDemoReplaySteps.some((step) =>
        step.tools.some((tool) => tool.toolName === "insertGraphEvidenceNode"),
      ),
    ).toBe(true);
    expect(carboplatinDemoReplaySteps.map((step) => step.label)).toEqual([
      "Map current evidence",
      "Search newer sources",
      "Update graph",
      "Prepare report context",
    ]);
    expect(running.toolCalls.map((toolCall) => toolCall.status)).toEqual([
      "complete",
      "complete",
      "complete",
      "running",
      "running",
      "running",
      "pending",
      "pending",
      "pending",
      "pending",
      "pending",
    ]);
    expect(running.workingNote).toBe("Searching newer evidence");
    expect(
      inserting.toolCalls.find((toolCall) => toolCall.id === "insert-times-india-node")?.status,
    ).toBe("running");
    expect(inserting.workingNote).toContain("graph mutation point");
    expect(inserting.source.url).toContain("timesofindia.indiatimes.com");
    expect(reportReady.reportContextReady).toBe(true);
    expect(reportReady.source.mode).toBe("scripted evidence");
    expect(reportReady.messages.at(-1)?.text).toBe(
      "Report context prepared: evidence, risk path, and recommended action are ready.",
    );
  });

  it("streams the Carboplatin demo with AI SDK tool and graph update chunks", async () => {
    const response = createCarboplatinDemoStreamResponse({
      timing: { reasoningDelayMs: 0, toolDelayMs: 0 },
    });
    const body = await response.text();
    const events = body
      .split("\n\n")
      .map((eventText) => eventText.replace(/^data: /, "").trim())
      .filter((eventText) => eventText && eventText !== "[DONE]")
      .map((eventText) => JSON.parse(eventText) as { toolCallId?: string; type: string });
    const insertOutputIndex = events.findIndex(
      (event) =>
        event.type === "tool-output-available" && event.toolCallId === "insert-times-india-node",
    );
    const graphUpdateIndex = events.findIndex((event) => event.type === "data-graph-update");
    const connectOutputIndex = events.findIndex(
      (event) =>
        event.type === "tool-output-available" && event.toolCallId === "connect-api-source",
    );

    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(body).toContain('"type":"start-step"');
    expect(body).toContain('"type":"tool-input-available"');
    expect(body).toContain('"type":"tool-output-available"');
    expect(body).toContain('"type":"data-agent-reasoning"');
    expect(body).toContain('"type":"data-graph-update"');
    expect(body).toContain('"type":"data-report-ready"');
    expect(body).toContain("source-times-india-2026");
    expect(insertOutputIndex).toBeGreaterThan(-1);
    expect(graphUpdateIndex).toBeGreaterThan(insertOutputIndex);
    expect(graphUpdateIndex).toBeLessThan(connectOutputIndex);
  });

  it("uses lower-temperature tighter-step runtime defaults in demo mode", () => {
    const defaultAgent = createSupplyRiskAgent();
    const demoAgent = createSupplyRiskAgent({ scenario: carboplatinDemoScenario });
    const defaultSettings = (
      defaultAgent as unknown as {
        settings: {
          stopWhen: (input: { steps: unknown[] }) => boolean;
          temperature: number;
        };
      }
    ).settings;
    const demoSettings = (
      demoAgent as unknown as {
        settings: {
          stopWhen: (input: { steps: unknown[] }) => boolean;
          temperature: number;
        };
      }
    ).settings;

    expect(defaultSettings.temperature).toBe(0.2);
    expect(defaultSettings.stopWhen({ steps: Array.from({ length: 8 }) })).toBe(true);
    expect(demoSettings.temperature).toBe(0.1);
    expect(demoSettings.stopWhen({ steps: Array.from({ length: 5 }) })).toBe(true);
    expect(demoSettings.stopWhen({ steps: Array.from({ length: 8 }) })).toBe(false);
  });

  it("validates the agent API scenario request contract", () => {
    expect(
      agentRequestSchema.safeParse({
        messages: [],
        scenario: carboplatinDemoScenario,
        selectedNodeId: "event-fda-shortage",
      }).success,
    ).toBe(true);
    expect(
      agentRequestSchema.safeParse({
        messages: [],
        scenario: "freeform-research",
      }).success,
    ).toBe(false);
  });

  it("reports missing Claude Managed Agents configuration", () => {
    const config = resolveClaudeManagedAgentConfig({});

    expect(config).toEqual({
      configured: false,
      missing: ["apiKey", "agentId", "environmentId"],
    });
  });

  it("starts a Claude Managed Agents investigation through the documented session API", async () => {
    const calls: Array<{ body: unknown; headers: Headers; method: string; url: string }> = [];
    const fetchImplementation: typeof fetch = async (url, init) => {
      const requestUrl = typeof url === "string" || url instanceof URL ? url.toString() : url.url;
      const requestBody = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;

      calls.push({
        body: requestBody,
        headers: new Headers(init?.headers),
        method: init?.method ?? "GET",
        url: requestUrl,
      });

      if (requestUrl.endsWith("/v1/sessions")) {
        return Response.json({ id: "sesn_123", status: "created" });
      }

      return Response.json({ ok: true });
    };
    const client = new ClaudeManagedAgentClient(
      {
        agentId: "agent_123",
        apiKey: "test-key",
        baseUrl: "https://api.example.test",
        environmentId: "env_123",
      },
      fetchImplementation,
    );

    const result = await startClaudeManagedSourceInvestigation(
      { nodeId: "supplier-accord-intas", question: "Investigate current filings." },
      { client },
    );

    expect(result).toEqual({
      configured: true,
      provider: "claude-managed-agents",
      sessionId: "sesn_123",
      status: "started",
      streamUrl: "https://api.example.test/v1/sessions/sesn_123/stream",
    });
    expect(calls).toHaveLength(2);
    expect(calls[0]?.url).toBe("https://api.example.test/v1/sessions");
    expect(calls[0]?.body).toEqual({ agent: "agent_123", environment_id: "env_123" });
    expect(calls[0]?.headers.get("anthropic-beta")).toBe(claudeManagedAgentsBetaHeader);
    expect(calls[0]?.headers.get("x-api-key")).toBe("test-key");
    expect(calls[1]?.url).toBe("https://api.example.test/v1/sessions/sesn_123/events");
    expect(calls[1]?.body).toEqual({
      events: [
        {
          type: "user.message",
          content: [
            expect.objectContaining({
              text: expect.stringContaining("Investigate current filings."),
              type: "text",
            }),
          ],
        },
      ],
    });
  });
});
