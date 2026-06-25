import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vite-plus/test";

import {
  answerSupplyGraphQuestion,
  buildNodeInvestigationPrompt,
  buildSupplyRiskAgentInstructions,
  ClaudeManagedAgentClient,
  claudeManagedAgentsBetaHeader,
  createSupplyRiskAgent,
  defaultSupplyRiskAgentModel,
  getSupplyGraphData,
  getSupplyGraphNodeContext,
  getSupplyRiskAgentModelId,
  listSupplyGraphNeighbors,
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

    expect(results).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "supplier-accord-intas",
          kind: "supplier",
          risk: "critical",
        }),
      ]),
    );
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

  it("merges exported platform graph nodes into graph tools", () => {
    const previousSnapshotPath = process.env.PLATFORM_GRAPH_SNAPSHOT_PATH;
    const tempDir = mkdtempSync(join(tmpdir(), "sanitas-graph-"));
    const snapshotPath = join(tempDir, "supply-chain-graph.json");

    writeFileSync(
      snapshotPath,
      JSON.stringify({
        dataStatus: {
          evidence: "Exported from test Neo4j graph.",
          limits: "Fixture snapshot.",
          mode: "neo4j_snapshot",
        },
        edges: [
          {
            confidence: 0.95,
            evidenceCount: 1,
            from: "Drug:test-sennosides",
            id: "Drug:test-sennosides|LABELS|Manufacturer:test-labeler",
            label: "LABELS",
            to: "Manufacturer:test-labeler",
          },
        ],
        generatedAt: "2026-06-25T12:00:00Z",
        nodes: [
          {
            attributes: { "Evidence span id": "span-1" },
            chainIds: ["neo4j-live"],
            confidence: 0.98,
            id: "Drug:test-sennosides",
            kind: "Drug",
            label: "Test Sennosides",
            risk: "watch",
            source: "source-run-1",
            status: "active",
            subtitle: "Neo4j drug",
            x: 50,
            y: 45,
          },
          {
            attributes: { "Source document id": "doc-1" },
            chainIds: ["neo4j-live"],
            confidence: 0.91,
            id: "Manufacturer:test-labeler",
            kind: "Manufacturer",
            label: "Test Labeler",
            risk: "low",
            source: "source-run-1",
            status: "active",
            subtitle: "Neo4j manufacturer",
            x: 54,
            y: 47,
          },
        ],
        summary: {
          graphNodes: 2,
          graphRelationships: 1,
          liveSources: 1,
          watchSignals: 1,
        },
      }),
      "utf8",
    );

    try {
      process.env.PLATFORM_GRAPH_SNAPSHOT_PATH = snapshotPath;

      expect(getSupplyGraphData().stats.platformNodes).toBe(2);
      expect(getSupplyGraphData().stats.sourceGraphNodes).toBe(2);
      expect(getSupplyGraphData().stats.sourceGraphRelationships).toBe(1);
      expect(searchSupplyGraph({ query: "test sennosides" })).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            id: "platform:Drug:test-sennosides",
            label: "Test Sennosides",
            risk: "watch",
          }),
        ]),
      );
      expect(listSupplyGraphNeighbors("platform:Drug:test-sennosides")).toEqual([
        expect.objectContaining({ id: "platform:Manufacturer:test-labeler" }),
      ]);
      const answer = answerSupplyGraphQuestion({
        nodeId: "platform:Drug:test-sennosides",
        question: "What evidence connects the labeler?",
      });

      expect(answer.answer).toContain("Test Sennosides");
      expect(answer.audit.auditType).toBe("dashboard.graph_chat_answer");
      expect(answer.audit.eventType).toBe("dashboard.graph_chat_answered");
      expect(answer.audit.topic).toBe("dashboard.graph_chat_answered");
      expect(answer.audit.inputHash).toHaveLength(64);
      expect(answer.audit.outputHash).toHaveLength(64);
      expect(answer.audit.metadata.graphDataMode).toBe("platform_snapshot");
      expect(answer.audit.metadata.snapshotGeneratedAt).toBe("2026-06-25T12:00:00Z");
      expect(answer.audit.metadata.snapshotMode).toBe("neo4j_snapshot");
      expect(answer.audit.metadata.sourceGraphNodes).toBe(2);
      expect(answer.audit.metadata.sourceGraphRelationships).toBe(1);
      expect(answer.audit.neighborNodeIds).toEqual(["platform:Manufacturer:test-labeler"]);
      expect(answer.audit.safety.clinicalAdvice).toBe(false);
      expect(answer.answer).toContain("Current platform snapshot: neo4j snapshot");
    } finally {
      if (previousSnapshotPath === undefined) {
        delete process.env.PLATFORM_GRAPH_SNAPSHOT_PATH;
      } else {
        process.env.PLATFORM_GRAPH_SNAPSHOT_PATH = previousSnapshotPath;
      }
      rmSync(tempDir, { force: true, recursive: true });
    }
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
