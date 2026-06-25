import { tool } from "ai";
import { z } from "zod";

import {
  startClaudeManagedSourceInvestigation,
  type StartClaudeManagedSourceInvestigationOptions,
} from "./claude-managed-agent";
import {
  getSupplyGraphNodeContext,
  graphNodeKindSchema,
  listPrioritySupplyRisks,
  riskLevelSchema,
  searchSupplyGraph,
} from "./supply-graph";

export type CreateSupplyRiskAgentToolsOptions = {
  managedInvestigation?: StartClaudeManagedSourceInvestigationOptions;
};

export function createSupplyRiskAgentTools(options: CreateSupplyRiskAgentToolsOptions = {}) {
  return {
    getNodeContext: tool({
      description:
        "Get detailed evidence, confidence, prompts, and source links for one supply graph node.",
      inputSchema: z.object({
        nodeId: z.string().describe("A supply graph node id returned by searchSupplyGraph."),
      }),
      execute: async ({ nodeId }) => getSupplyGraphNodeContext(nodeId),
    }),
    listPriorityRisks: tool({
      description:
        "List the highest-priority non-stable risks in the current medicine supply graph.",
      inputSchema: z.object({
        limit: z.number().int().min(1).max(12).optional(),
      }),
      execute: async ({ limit }) => listPrioritySupplyRisks(limit),
    }),
    searchSupplyGraph: tool({
      description:
        "Search the medicine supply-risk graph by medicine, component, supplier, event, place, source, or risk wording.",
      inputSchema: z.object({
        kinds: z.array(graphNodeKindSchema).optional(),
        limit: z.number().int().min(1).max(12).optional(),
        query: z
          .string()
          .describe("Search text such as a medicine, supplier, event, source, or location."),
        riskLevels: z.array(riskLevelSchema).optional(),
      }),
      execute: async (input) => searchSupplyGraph(input),
    }),
    startManagedSourceInvestigation: tool({
      description:
        "Start or resume a Claude Managed Agents session to investigate live external sources for a selected supply graph node. Use this when the user asks to further investigate, find new sources, add graph nodes, or create new evidence-backed connections.",
      inputSchema: z.object({
        maxSources: z.number().int().min(1).max(20).optional(),
        nodeId: z.string().describe("The selected supply graph node id to investigate."),
        question: z.string().optional().describe("The user's focused investigation request."),
        sessionId: z
          .string()
          .optional()
          .describe("Existing Claude Managed Agents session id to resume."),
      }),
      execute: async (input) =>
        startClaudeManagedSourceInvestigation(input, options.managedInvestigation),
    }),
  };
}

export const supplyRiskAgentTools = createSupplyRiskAgentTools();
