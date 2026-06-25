import { describe, expect, it } from "vite-plus/test";

import {
  buildNodeInvestigationPrompt,
  buildSupplyRiskAgentInstructions,
  ClaudeManagedAgentClient,
  claudeManagedAgentsBetaHeader,
  createSupplyRiskAgent,
  defaultSupplyRiskAgentModel,
  getSupplyGraphNodeContext,
  getSupplyRiskAgentModelId,
  listPrioritySupplyRisks,
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
    expect(getSupplyRiskAgentModelId("openai/gpt-5.1")).toBe("openai/gpt-5.1");
  });

  it("keeps instructions grounded in agent behavior", () => {
    const instructions = buildSupplyRiskAgentInstructions(new Date("2026-06-25T00:00:00.000Z"));

    expect(instructions).toContain("Today is 2026-06-25");
    expect(instructions).toContain("Use the supply graph tools");
    expect(instructions).toContain("delegate live external source investigation");
    expect(instructions).toContain("never provide clinical treatment advice");
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
