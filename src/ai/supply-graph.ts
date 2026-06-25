import { createHash, randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { z } from "zod";

import {
  graphEdges,
  graphNodes,
  nodeDetails,
  type GraphEdge,
  type GraphNode,
  type NodeDetails,
  type RiskLevel,
} from "#/data/carboplatin-risk-scenario";
import {
  buildPlatformGraphData,
  type PlatformGraphData,
  type PlatformGraphSnapshotMode,
  type PlatformGraphSnapshot,
} from "#/data/platform-graph-snapshot";

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
      details: NodeDetails[string] | null;
      found: true;
      node: SupplyGraphNodeSummary;
    }
  | {
      found: false;
      knownNodeIds: string[];
    };

export type SupplyGraphData = {
  details: NodeDetails;
  edges: GraphEdge[];
  nodes: GraphNode[];
  platformGraph: PlatformGraphData | null;
  stats: {
    curatedNodes: number;
    edges: number;
    liveSources: number;
    nodes: number;
    platformEdges: number;
    platformNodes: number;
    sourceGraphNodes: number;
    sourceGraphRelationships: number;
    watchSignals: number;
  };
};

export type SupplyGraphNeighbor = SupplyGraphNodeSummary & {
  edgeId: string;
  relationshipRisk: RiskLevel;
};

export type SupplyGraphQuestionInput = {
  limit?: number;
  nodeId?: string;
  question: string;
};

export type SupplyGraphQuestionResponse = {
  answer: string;
  audit: GraphChatAuditRecord;
  graphStats: SupplyGraphData["stats"];
  neighbors: SupplyGraphNeighbor[];
  relatedNodes: SupplyGraphNodeSummary[];
  selectedNode: SupplyGraphNodeContext | null;
  sources: { meta: string; title: string; url: string }[];
};

export type GraphChatAuditRecord = {
  auditId: string;
  auditType: "dashboard.graph_chat_answer";
  correlationId: string;
  createdAt: string;
  eventType: "dashboard.graph_chat_answered";
  graphStats: SupplyGraphData["stats"];
  idempotencyKey: string;
  inputHash: string;
  inputLength: number;
  metadata: {
    graphDataMode: "curated_fallback" | "platform_snapshot";
    outputMode: "deterministic_graph_summary";
    platformEdges: number;
    platformNodes: number;
    liveSources: number;
    snapshotGeneratedAt: string | null;
    snapshotMode: "none" | "unknown_snapshot" | PlatformGraphSnapshotMode;
    sourceGraphNodes: number;
    sourceGraphRelationships: number;
    watchSignals: number;
  };
  neighborNodeIds: string[];
  nodeId?: string;
  outputHash: string;
  outputSchema: "SupplyGraphQuestionResponse";
  outputSchemaVersion: 1;
  relatedNodeIds: string[];
  safety: {
    adviceScope: "supply_chain_intelligence_only";
    clinicalAdvice: false;
    patientIdentifiableData: false;
  };
  selectedNodeId: string | null;
  service: "dashboard-graph-chat";
  sourceRefs: { meta: string; title: string; url: string }[];
  status: "succeeded";
  topic: "dashboard.graph_chat_answered";
};

const defaultPlatformGraphSnapshotPath = join(
  process.cwd(),
  "public",
  "platform-demo",
  "supply-chain-graph.json",
);

function readPlatformGraphSnapshot(): PlatformGraphSnapshot | null {
  const snapshotPath = process.env.PLATFORM_GRAPH_SNAPSHOT_PATH || defaultPlatformGraphSnapshotPath;

  if (!existsSync(snapshotPath)) {
    return null;
  }

  return JSON.parse(readFileSync(snapshotPath, "utf8")) as PlatformGraphSnapshot;
}

export function getSupplyGraphData(snapshot = readPlatformGraphSnapshot()): SupplyGraphData {
  const platformGraph = snapshot ? buildPlatformGraphData(snapshot) : null;
  const nodes = platformGraph ? [...graphNodes, ...platformGraph.nodes] : graphNodes;
  const edges = platformGraph ? [...graphEdges, ...platformGraph.edges] : graphEdges;
  const details = platformGraph ? { ...nodeDetails, ...platformGraph.details } : nodeDetails;
  const snapshotSummary = platformGraph?.snapshot.summary;

  return {
    details,
    edges,
    nodes,
    platformGraph,
    stats: {
      curatedNodes: graphNodes.length,
      edges: edges.length,
      liveSources: snapshotSummary?.liveSources ?? 0,
      nodes: nodes.length,
      platformEdges: platformGraph?.edges.length ?? 0,
      platformNodes: platformGraph?.nodes.length ?? 0,
      sourceGraphNodes: snapshotSummary?.graphNodes ?? platformGraph?.nodes.length ?? 0,
      sourceGraphRelationships:
        snapshotSummary?.graphRelationships ?? platformGraph?.edges.length ?? 0,
      watchSignals: snapshotSummary?.watchSignals ?? 0,
    },
  };
}

function snapshotModeFor(graph: SupplyGraphData) {
  if (!graph.platformGraph) {
    return "none";
  }

  return graph.platformGraph.snapshot.dataStatus?.mode ?? "unknown_snapshot";
}

function toSearchText(node: GraphNode, detailsById: NodeDetails) {
  const details = detailsById[node.id];
  const facts = details?.facts.join(" ") ?? "";
  const sources =
    details?.sources.map((source) => `${source.title} ${source.meta}`).join(" ") ?? "";

  return `${node.label} ${node.kind} ${node.risk} ${node.summary} ${facts} ${sources}`.toLowerCase();
}

function hashJson(value: unknown) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
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
  const graph = getSupplyGraphData();
  const query = input.query.trim().toLowerCase();
  const limit = clampSupplyGraphLimit(input.limit, 6);
  const kindFilter = new Set(input.kinds);
  const riskFilter = new Set(input.riskLevels);

  return graph.nodes
    .filter((node) => kindFilter.size === 0 || kindFilter.has(node.kind))
    .filter((node) => riskFilter.size === 0 || riskFilter.has(node.risk))
    .map((node) => {
      const text = toSearchText(node, graph.details);
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
  const graph = getSupplyGraphData();
  const node = graph.nodes.find((candidate) => candidate.id === nodeId);

  if (!node) {
    return {
      found: false,
      knownNodeIds: graph.nodes.slice(0, 80).map((candidate) => candidate.id),
    };
  }

  return {
    found: true,
    node: summarizeSupplyGraphNode(node),
    details: graph.details[node.id] ?? null,
  };
}

export function listSupplyGraphNeighbors(nodeId: string, limit = 8): SupplyGraphNeighbor[] {
  const graph = getSupplyGraphData();
  const normalizedLimit = clampSupplyGraphLimit(limit, 8);
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));

  return graph.edges
    .flatMap((edge): SupplyGraphNeighbor[] => {
      if (edge.from === nodeId) {
        const node = byId.get(edge.to);
        return node
          ? [{ ...summarizeSupplyGraphNode(node), edgeId: edge.id, relationshipRisk: edge.risk }]
          : [];
      }
      if (edge.to === nodeId) {
        const node = byId.get(edge.from);
        return node
          ? [{ ...summarizeSupplyGraphNode(node), edgeId: edge.id, relationshipRisk: edge.risk }]
          : [];
      }
      return [];
    })
    .sort(
      (first, second) =>
        riskRank[second.relationshipRisk] - riskRank[first.relationshipRisk] ||
        riskRank[second.risk] - riskRank[first.risk] ||
        first.label.localeCompare(second.label),
    )
    .slice(0, normalizedLimit);
}

export function listPrioritySupplyRisks(limit = 6) {
  const graph = getSupplyGraphData();

  return graph.nodes
    .filter((node) => node.risk !== "stable")
    .sort(
      (first, second) =>
        riskRank[second.risk] - riskRank[first.risk] || first.label.localeCompare(second.label),
    )
    .slice(0, clampSupplyGraphLimit(limit, 6))
    .map((node) => summarizeSupplyGraphNode(node));
}

export function answerSupplyGraphQuestion(
  input: SupplyGraphQuestionInput,
): SupplyGraphQuestionResponse {
  const graph = getSupplyGraphData();
  const limit = clampSupplyGraphLimit(input.limit, 5);
  const selectedNode = input.nodeId ? getSupplyGraphNodeContext(input.nodeId) : null;
  const relatedNodes = searchSupplyGraph({ limit, query: input.question }).filter(
    (node) => node.id !== input.nodeId,
  );
  const neighbors =
    selectedNode && selectedNode.found ? listSupplyGraphNeighbors(selectedNode.node.id, 6) : [];
  const selectedSources = selectedNode?.found ? (selectedNode.details?.sources ?? []) : [];
  const relatedSources = relatedNodes.flatMap((node) => graph.details[node.id]?.sources ?? []);
  const sources = [...selectedSources, ...relatedSources].slice(0, 6);
  const selectedSummary =
    selectedNode && selectedNode.found
      ? `${selectedNode.node.label} is a ${selectedNode.node.kind} node with ${selectedNode.node.risk} risk. ${selectedNode.details?.whyItMatters ?? selectedNode.node.summary}`
      : "No selected graph node was found for this question.";
  const neighborSummary = neighbors.length
    ? `Connected nodes include ${neighbors
        .slice(0, 4)
        .map((node) => `${node.label} (${node.kind}, ${node.risk})`)
        .join(", ")}.`
    : "No direct neighbors are visible in the current graph snapshot.";
  const relatedSummary = relatedNodes.length
    ? `Relevant search matches include ${relatedNodes
        .slice(0, 4)
        .map((node) => `${node.label} (${node.kind}, ${node.risk})`)
        .join(", ")}.`
    : "No additional graph nodes matched the question text.";
  const snapshotMode = snapshotModeFor(graph);
  const snapshotSummary = graph.platformGraph
    ? `Current platform snapshot: ${snapshotMode.replaceAll("_", " ")}, generated ${graph.platformGraph.snapshot.generatedAt}, source graph ${graph.stats.sourceGraphNodes} nodes and ${graph.stats.sourceGraphRelationships} relationships.`
    : "No platform snapshot is loaded; using the curated fallback graph only.";
  const answer = `${selectedSummary} ${neighborSummary} ${relatedSummary} ${snapshotSummary} This summarizes graph evidence and provenance, not clinical advice.`;
  const inputHash = hashJson({
    limit,
    nodeId: input.nodeId ?? null,
    question: input.question,
  });
  const outputHash = hashJson({
    answer,
    graphStats: graph.stats,
    neighbors,
    relatedNodes,
    selectedNode,
    sources,
  });
  const idempotencyKey = `dashboard.graph_chat_answer:${inputHash}:${outputHash}`;
  const audit: GraphChatAuditRecord = {
    auditId: randomUUID(),
    auditType: "dashboard.graph_chat_answer",
    correlationId: randomUUID(),
    createdAt: new Date().toISOString(),
    eventType: "dashboard.graph_chat_answered",
    graphStats: graph.stats,
    idempotencyKey,
    inputHash,
    inputLength: input.question.length,
    metadata: {
      graphDataMode: graph.platformGraph ? "platform_snapshot" : "curated_fallback",
      outputMode: "deterministic_graph_summary",
      liveSources: graph.stats.liveSources,
      platformEdges: graph.stats.platformEdges,
      platformNodes: graph.stats.platformNodes,
      snapshotGeneratedAt: graph.platformGraph?.snapshot.generatedAt ?? null,
      snapshotMode,
      sourceGraphNodes: graph.stats.sourceGraphNodes,
      sourceGraphRelationships: graph.stats.sourceGraphRelationships,
      watchSignals: graph.stats.watchSignals,
    },
    neighborNodeIds: neighbors.map((node) => node.id),
    nodeId: input.nodeId,
    outputHash,
    outputSchema: "SupplyGraphQuestionResponse",
    outputSchemaVersion: 1,
    relatedNodeIds: relatedNodes.map((node) => node.id),
    safety: {
      adviceScope: "supply_chain_intelligence_only",
      clinicalAdvice: false,
      patientIdentifiableData: false,
    },
    selectedNodeId: selectedNode?.found ? selectedNode.node.id : null,
    service: "dashboard-graph-chat",
    sourceRefs: sources,
    status: "succeeded",
    topic: "dashboard.graph_chat_answered",
  };

  return {
    answer,
    audit,
    graphStats: graph.stats,
    neighbors,
    relatedNodes,
    selectedNode,
    sources,
  };
}
