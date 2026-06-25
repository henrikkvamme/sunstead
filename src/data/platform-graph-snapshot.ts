import type { GraphEdge, GraphNode, NodeDetails, RiskLevel } from "./carboplatin-risk-scenario";

export const platformGraphSnapshotUrl = "/platform-demo/supply-chain-graph.json";
const platformPrefix = "platform:";

type PlatformNodeKind =
  | "ActiveIngredient"
  | "Drug"
  | "Facility"
  | "LogisticsPressureObservation"
  | "Location"
  | "Manufacturer"
  | "MedicalDevice"
  | "NDC"
  | "NewsSignal"
  | "PriceObservation"
  | "Recall"
  | "RegulatoryAgency"
  | "RegulatoryNotice"
  | "Shortage"
  | "Source"
  | "Supplier";

type PlatformRiskLevel = "high" | "low" | "medium" | "watch";
export type PlatformGraphSnapshotMode = "file_snapshot" | "neo4j_snapshot";

type PlatformGraphNode = {
  attributes: Record<string, string>;
  chainIds: string[];
  confidence: number;
  id: string;
  kind: PlatformNodeKind;
  label: string;
  risk?: PlatformRiskLevel;
  source: string;
  status: string;
  subtitle?: string;
  x: number;
  y: number;
};

type PlatformGraphEdge = {
  confidence: number;
  evidenceCount: number;
  from: string;
  id: string;
  label: string;
  to: string;
};

export type PlatformGraphSnapshot = {
  dataStatus?: {
    evidence: string;
    limits: string;
    mode: PlatformGraphSnapshotMode;
  };
  edges: PlatformGraphEdge[];
  generatedAt: string;
  nodes: PlatformGraphNode[];
  summary: {
    graphNodes: number;
    graphRelationships: number;
    liveSources: number;
    watchSignals: number;
  };
};

export type PlatformGraphData = {
  details: NodeDetails;
  edges: GraphEdge[];
  medicineSupplyChainEdges: Record<string, string[]>;
  nodes: GraphNode[];
  snapshot: PlatformGraphSnapshot;
};

export function isPlatformNodeId(nodeId: string) {
  return nodeId.startsWith(platformPrefix);
}

export function platformNodeId(nodeId: string) {
  return `${platformPrefix}${nodeId}`;
}

export function buildPlatformGraphData(snapshot: PlatformGraphSnapshot): PlatformGraphData {
  const nodes = snapshot.nodes.map(mapPlatformNode);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = snapshot.edges
    .map((edge) => mapPlatformEdge(edge, snapshot))
    .filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to));
  const details = Object.fromEntries(
    snapshot.nodes.map((node) => [platformNodeId(node.id), buildNodeDetails(node, snapshot)]),
  );
  const medicineSupplyChainEdges: Record<string, string[]> = {};

  for (const node of nodes) {
    if (node.kind !== "medicine") {
      continue;
    }

    medicineSupplyChainEdges[node.id] = edges
      .filter((edge) => edge.from === node.id || edge.to === node.id)
      .map((edge) => edge.id);
  }

  return {
    details,
    edges,
    medicineSupplyChainEdges,
    nodes,
    snapshot,
  };
}

function mapPlatformNode(node: PlatformGraphNode): GraphNode {
  const x = clamp(node.x, 6, 94);
  const y = clamp(node.y, 8, 92);

  return {
    detail: { x, y },
    id: platformNodeId(node.id),
    kind: mapNodeKind(node.kind),
    label: node.label,
    metric: nodeMetric(node),
    overview: { x, y },
    risk: mapRisk(node.risk),
    riskReason: `${node.source} ${node.kind} evidence, ${node.status}, ${Math.round(
      node.confidence * 100,
    )}% confidence.`,
    riskScore: platformRiskScore(node.risk, node.confidence),
    summary: node.subtitle || `${node.kind} from ${node.source}`,
  };
}

function mapPlatformEdge(edge: PlatformGraphEdge, snapshot: PlatformGraphSnapshot): GraphEdge {
  return {
    from: platformNodeId(edge.from),
    id: platformNodeId(edge.id),
    risk: edgeRisk(edge, snapshot),
    to: platformNodeId(edge.to),
  };
}

function buildNodeDetails(
  node: PlatformGraphNode,
  snapshot: PlatformGraphSnapshot,
): NodeDetails[string] {
  const facts = [
    `Source: ${node.source}`,
    `Status: ${node.status}`,
    `Confidence: ${Math.round(node.confidence * 100)}%`,
    ...Object.entries(node.attributes).map(([key, value]) => `${key}: ${value}`),
  ];
  const evidence = snapshot.dataStatus?.evidence ?? "Loaded from the platform graph snapshot.";
  const limits = snapshot.dataStatus?.limits ?? "Snapshot can be refreshed from Neo4j export.";

  return {
    confidence: `${Math.round(node.confidence * 100)}% platform confidence`,
    facts,
    prompts: [
      "Show connected platform nodes",
      "Explain source provenance",
      "Refresh from Neo4j",
      "Check related risks",
    ],
    sources: [
      {
        meta: `${node.source}, ${snapshot.generatedAt}`,
        title: `${node.label} platform graph evidence`,
        url: platformGraphSnapshotUrl,
      },
    ],
    whyItMatters: `${evidence} ${limits}`,
  };
}

function mapNodeKind(kind: PlatformNodeKind): GraphNode["kind"] {
  if (kind === "Drug") {
    return "medicine";
  }
  if (kind === "MedicalDevice") {
    return "component";
  }
  if (kind === "ActiveIngredient") {
    return "component";
  }
  if (kind === "Manufacturer" || kind === "Supplier") {
    return "supplier";
  }
  if (kind === "Facility" || kind === "Location") {
    return "place";
  }
  if (kind === "Source" || kind === "NDC" || kind === "RegulatoryAgency") {
    return "source";
  }
  return "event";
}

function platformRiskScore(risk: PlatformRiskLevel | undefined, confidence: number): number {
  const base = risk === "high" ? 82 : risk === "medium" ? 64 : risk === "watch" ? 46 : 22;
  const confidenceAdjustment = Math.round((confidence - 0.5) * 12);

  return clamp(base + confidenceAdjustment, 12, 95);
}

function mapRisk(risk: PlatformRiskLevel | undefined): RiskLevel {
  if (risk === "high") {
    return "critical";
  }
  if (risk === "medium") {
    return "elevated";
  }
  if (risk === "watch") {
    return "watch";
  }
  return "stable";
}

function edgeRisk(edge: PlatformGraphEdge, snapshot: PlatformGraphSnapshot): RiskLevel {
  const from = snapshot.nodes.find((node) => node.id === edge.from);
  const to = snapshot.nodes.find((node) => node.id === edge.to);
  const risks = [mapRisk(from?.risk), mapRisk(to?.risk)];

  if (risks.includes("critical")) {
    return "critical";
  }
  if (risks.includes("elevated")) {
    return "elevated";
  }
  if (risks.includes("watch")) {
    return "watch";
  }
  return "stable";
}

function nodeMetric(node: PlatformGraphNode): string | undefined {
  if (node.kind === "PriceObservation") {
    return node.attributes.Value;
  }
  if (node.kind === "NDC") {
    return "NDC";
  }
  if (node.kind === "Source") {
    return node.status;
  }
  if (node.kind === "Recall") {
    return node.status;
  }
  if (node.kind === "Shortage") {
    return "shortage";
  }
  return undefined;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
