import { z } from "zod";

import {
  graphNodes,
  nodeDetails,
  type GraphNode,
  type RiskLevel,
} from "#/data/carboplatin-risk-scenario";

export const riskRank: Record<RiskLevel, number> = {
  critical: 4,
  elevated: 3,
  watch: 2,
  stable: 1,
};

export const graphNodeKindSchema = z.enum([
  "component",
  "event",
  "medicine",
  "place",
  "source",
  "supplier",
]);

export const riskLevelSchema = z.enum(["critical", "elevated", "stable", "watch"]);

export type SupplyGraphSearchInput = {
  kinds?: GraphNode["kind"][];
  limit?: number;
  query: string;
  riskLevels?: RiskLevel[];
};

export type SupplyGraphNodeSummary = {
  id: string;
  kind: GraphNode["kind"];
  label: string;
  metric?: string;
  risk: RiskLevel;
  summary: string;
};

export type SupplyGraphNodeContext =
  | {
      details: (typeof nodeDetails)[string] | null;
      found: true;
      node: SupplyGraphNodeSummary;
    }
  | {
      found: false;
      knownNodeIds: string[];
    };

function toSearchText(node: GraphNode) {
  const details = nodeDetails[node.id];
  const facts = details?.facts.join(" ") ?? "";
  const sources =
    details?.sources.map((source) => `${source.title} ${source.meta}`).join(" ") ?? "";

  return `${node.label} ${node.kind} ${node.risk} ${node.summary} ${facts} ${sources}`.toLowerCase();
}

export function clampSupplyGraphLimit(limit: number | undefined, fallback: number) {
  if (limit === undefined) {
    return fallback;
  }

  return Math.min(Math.max(Math.trunc(limit), 1), 12);
}

export function summarizeSupplyGraphNode(node: GraphNode): SupplyGraphNodeSummary {
  return {
    id: node.id,
    kind: node.kind,
    label: node.label,
    metric: node.metric,
    risk: node.risk,
    summary: node.summary,
  };
}

export function searchSupplyGraph(input: SupplyGraphSearchInput) {
  const query = input.query.trim().toLowerCase();
  const limit = clampSupplyGraphLimit(input.limit, 6);
  const kindFilter = new Set(input.kinds);
  const riskFilter = new Set(input.riskLevels);

  return graphNodes
    .filter((node) => kindFilter.size === 0 || kindFilter.has(node.kind))
    .filter((node) => riskFilter.size === 0 || riskFilter.has(node.risk))
    .map((node) => {
      const text = toSearchText(node);
      const labelMatch = node.label.toLowerCase().includes(query);
      const textMatch = query.length === 0 || text.includes(query);
      const score = (labelMatch ? 3 : 0) + (textMatch ? 1 : 0) + riskRank[node.risk];

      return { node, score, textMatch };
    })
    .filter((candidate) => candidate.textMatch)
    .sort(
      (first, second) =>
        second.score - first.score || first.node.label.localeCompare(second.node.label),
    )
    .slice(0, limit)
    .map(({ node }) => summarizeSupplyGraphNode(node));
}

export function getSupplyGraphNodeContext(nodeId: string): SupplyGraphNodeContext {
  const node = graphNodes.find((candidate) => candidate.id === nodeId);

  if (!node) {
    return {
      found: false,
      knownNodeIds: graphNodes.map((candidate) => candidate.id),
    };
  }

  return {
    found: true,
    node: summarizeSupplyGraphNode(node),
    details: nodeDetails[node.id] ?? null,
  };
}

export function listPrioritySupplyRisks(limit = 6) {
  return graphNodes
    .filter((node) => node.risk !== "stable")
    .sort(
      (first, second) =>
        riskRank[second.risk] - riskRank[first.risk] || first.label.localeCompare(second.label),
    )
    .slice(0, clampSupplyGraphLimit(limit, 6))
    .map((node) => summarizeSupplyGraphNode(node));
}
