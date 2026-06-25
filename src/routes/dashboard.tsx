import { createFileRoute } from "@tanstack/react-router";
import {
  Activity,
  Bell,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ExternalLink,
  Factory,
  FileSearch,
  FileText,
  FlaskConical,
  Loader2,
  MapPin,
  Pill,
  Radar,
  Route as RouteIcon,
  Search,
  ShieldAlert,
  Sparkles,
  Workflow,
  Waves,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import {
  carboplatinDemoReplaySteps,
  carboplatinDemoScenario,
  getCarboplatinDemoReplayState,
} from "#/ai/carboplatin-demo";
import {
  carboplatinReportPreview,
  graphEdges,
  graphNodes,
  medicineSupplyChainEdges,
  nodeDetails,
  riskPathBase,
  scriptedSourceId,
  selectedMedicineId,
  selectedMedicineSlug,
  supplierRiskPath,
} from "#/data/carboplatin-risk-scenario";
import type { GraphEdge, GraphNode, NodeDetails } from "#/data/carboplatin-risk-scenario";
import { cn } from "#/lib/cn";

export const Route = createFileRoute("/dashboard")({
  component: Dashboard,
});

type GraphMode = "focused" | "overview";
type ViewMode = "investigating" | "medicine-focus" | "node-detail" | "overview" | "report-ready";

type CommandPaletteItem = {
  action: () => void;
  icon: ReactNode;
  id: string;
  meta: string;
  title: string;
  token: string;
};

type InvestigationStepStatus = "complete" | "pending" | "running";

type InvestigationStreamTool = {
  id: string;
  label: string;
  outputSummary?: string;
  status: InvestigationStepStatus;
  stepId: string;
  toolName: string;
};

type InvestigationReasoningSummary = {
  afterToolId?: string;
  beforeToolId?: string;
  id: string;
  status: "complete" | "streaming";
  text: string;
};

type InvestigationStreamStep = {
  id: string;
  label: string;
  reasoning: InvestigationReasoningSummary[];
  status: InvestigationStepStatus;
  summary?: string;
  toolCount: number;
  tools: InvestigationStreamTool[];
};

type AgentStreamPart =
  | {
      data: {
        id: string;
        label: string;
        status: InvestigationStepStatus;
        summary?: string;
        toolCount: number;
      };
      id?: string;
      type: "data-agent-step";
    }
  | {
      data: {
        id: string;
        label: string;
        outputSummary?: string;
        status: InvestigationStepStatus;
        stepId: string;
        toolName: string;
      };
      id?: string;
      type: "data-agent-tool";
    }
  | {
      data: {
        afterToolId?: string;
        beforeToolId?: string;
        id: string;
        status: "complete" | "streaming";
        stepId: string;
        text: string;
      };
      id?: string;
      type: "data-agent-reasoning";
    }
  | {
      data: {
        addedEvidenceNodeIds: string[];
        edgesToHighlight: string[];
        nodesToHighlight: string[];
        source: unknown;
      };
      id?: string;
      type: "data-graph-update";
    }
  | {
      data: {
        reportContextReady: true;
        sentence: string;
      };
      id?: string;
      type: "data-report-ready";
    };

function createInitialInvestigationSteps(): InvestigationStreamStep[] {
  return carboplatinDemoReplaySteps.map((step) => ({
    id: step.id,
    label: step.label,
    reasoning: [],
    status: "pending",
    toolCount: step.tools.length,
    tools: step.tools.map((tool) => ({
      id: tool.id,
      label: tool.label,
      outputSummary: undefined,
      status: "pending",
      stepId: step.id,
      toolName: tool.toolName,
    })),
  }));
}

function isAgentStreamPart(value: unknown): value is AgentStreamPart {
  if (typeof value !== "object" || value === null || !("type" in value)) {
    return false;
  }

  const type = (value as { type: unknown }).type;

  return (
    type === "data-agent-step" ||
    type === "data-agent-tool" ||
    type === "data-agent-reasoning" ||
    type === "data-graph-update" ||
    type === "data-report-ready"
  );
}

async function readAgentEventStream(
  body: ReadableStream<Uint8Array>,
  onPart: (part: AgentStreamPart) => void,
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    let eventBoundary = buffer.indexOf("\n\n");
    while (eventBoundary >= 0) {
      const eventText = buffer.slice(0, eventBoundary);
      buffer = buffer.slice(eventBoundary + 2);
      eventBoundary = buffer.indexOf("\n\n");

      for (const line of eventText.split("\n")) {
        if (!line.startsWith("data:")) {
          continue;
        }

        const rawData = line.slice(5).trim();
        if (!rawData || rawData === "[DONE]") {
          continue;
        }

        const parsed: unknown = JSON.parse(rawData);
        if (isAgentStreamPart(parsed)) {
          onPart(parsed);
        }
      }
    }

    if (done) {
      break;
    }
  }
}

const kindIcons: Record<GraphNode["kind"], ReactNode> = {
  component: <FlaskConical aria-hidden size={15} />,
  event: <Waves aria-hidden size={15} />,
  medicine: <Pill aria-hidden size={16} />,
  place: <MapPin aria-hidden size={15} />,
  source: <FileText aria-hidden size={14} />,
  supplier: <Factory aria-hidden size={15} />,
};

function riskScoreFor(item: GraphEdge | GraphNode) {
  if (typeof item.riskScore === "number") {
    return item.riskScore;
  }

  if (item.risk === "critical") {
    return 86;
  }

  if (item.risk === "elevated") {
    return 66;
  }

  if (item.risk === "watch") {
    return 44;
  }

  return 20;
}

function riskStyleFor(item: GraphEdge | GraphNode, extra?: CSSProperties) {
  const score = riskScoreFor(item);
  const intensity = Math.max(0.16, Math.min(0.88, score / 100));

  return {
    "--risk-alpha": intensity.toFixed(2),
    "--risk-score": String(score),
    ...extra,
  } as CSSProperties;
}

function detailsForNode(node: GraphNode): NodeDetails[string] {
  const directDetails = nodeDetails[node.id];

  if (directDetails) {
    return directDetails;
  }

  const connectedSourceIds = graphEdges
    .filter((edge) => edge.from === node.id || edge.to === node.id)
    .map((edge) => (edge.from === node.id ? edge.to : edge.from))
    .filter((id) =>
      graphNodes.some((candidate) => candidate.id === id && candidate.kind === "source"),
    );
  const connectedSources = connectedSourceIds.flatMap(
    (sourceId) => nodeDetails[sourceId]?.sources ?? [],
  );

  return {
    confidence: connectedSources.length > 0 ? "Evidence mapped" : "Scenario context",
    facts: [
      node.riskReason ?? node.summary,
      `${connectedSources.length} mapped evidence source${
        connectedSources.length === 1 ? "" : "s"
      } connected in the graph`,
      "This node is supporting context unless it belongs to the highlighted action path",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources:
      connectedSources.length > 0
        ? connectedSources
        : [
            {
              meta: "Scenario evidence pending",
              title: "Mapped evidence placeholder",
              url: "#",
            },
          ],
    whyItMatters:
      node.riskReason ??
      `${node.label} contributes to the mapped supply-risk context for Cisplatin Injection.`,
  };
}

function findSourceNodeForEvidence(source: NodeDetails[string]["sources"][number]) {
  return graphNodes.find((node) => {
    if (node.kind !== "source") {
      return false;
    }

    return nodeDetails[node.id]?.sources.some((candidate) => candidate.url === source.url);
  });
}

function sourceUrlForNode(nodeId: string) {
  return nodeDetails[nodeId]?.sources[0]?.url;
}

type LayoutPoint = { x: number; y: number };

function nodeFootprint(node: GraphNode, mode: GraphMode) {
  if (mode === "overview") {
    return node.kind === "medicine" ? { height: 4.9, width: 17.8 } : { height: 4.4, width: 4.4 };
  }

  if (node.kind === "source") {
    return { height: 4.8, width: 4.8 };
  }

  if (node.id === selectedMedicineId) {
    return { height: 8.6, width: 14.4 };
  }

  return { height: 8.1, width: 13.2 };
}

function nodeMobility(node: GraphNode) {
  if (node.kind === "source") {
    return 1.25;
  }

  if (node.actionPath || node.id === selectedMedicineId) {
    return 0.28;
  }

  return 0.86;
}

function clampLayoutPoint(point: LayoutPoint, node: GraphNode, mode: GraphMode) {
  const footprint = nodeFootprint(node, mode);
  const marginX = footprint.width / 2 + 1.2;
  const marginY = footprint.height / 2 + 1.2;

  point.x = Math.min(100 - marginX, Math.max(marginX, point.x));
  point.y = Math.min(100 - marginY, Math.max(marginY, point.y));
}

function removeNodeOverlaps(points: Map<string, LayoutPoint>, nodes: GraphNode[], mode: GraphMode) {
  const padding = mode === "overview" ? 1.2 : 1.7;

  for (let iteration = 0; iteration < 90; iteration += 1) {
    for (let index = 0; index < nodes.length; index += 1) {
      for (let nextIndex = index + 1; nextIndex < nodes.length; nextIndex += 1) {
        const first = nodes[index];
        const second = nodes[nextIndex];
        const firstPoint = points.get(first.id);
        const secondPoint = points.get(second.id);

        if (!firstPoint || !secondPoint) {
          continue;
        }

        const firstFootprint = nodeFootprint(first, mode);
        const secondFootprint = nodeFootprint(second, mode);
        const minX = (firstFootprint.width + secondFootprint.width) / 2 + padding;
        const minY = (firstFootprint.height + secondFootprint.height) / 2 + padding;
        const dx = secondPoint.x - firstPoint.x || 0.01;
        const dy = secondPoint.y - firstPoint.y || 0.01;
        const overlapX = minX - Math.abs(dx);
        const overlapY = minY - Math.abs(dy);

        if (overlapX <= 0 || overlapY <= 0) {
          continue;
        }

        const firstMobility = nodeMobility(first);
        const secondMobility = nodeMobility(second);
        const mobilityTotal = firstMobility + secondMobility;
        const firstShare = secondMobility / mobilityTotal;
        const secondShare = firstMobility / mobilityTotal;

        if (overlapX < overlapY) {
          const shift = overlapX * Math.sign(dx) * 0.58;
          firstPoint.x -= shift * firstShare;
          secondPoint.x += shift * secondShare;
        } else {
          const shift = overlapY * Math.sign(dy) * 0.58;
          firstPoint.y -= shift * firstShare;
          secondPoint.y += shift * secondShare;
        }
      }
    }

    for (const node of nodes) {
      const point = points.get(node.id);

      if (point) {
        clampLayoutPoint(point, node, mode);
      }
    }
  }
}

function buildOverviewLayout(nodes: GraphNode[]) {
  const points = new Map(nodes.map((node) => [node.id, { ...node.overview }]));
  const visibleNodes = nodes.filter((node) => points.has(node.id));

  for (let iteration = 0; iteration < 96; iteration += 1) {
    for (let index = 0; index < visibleNodes.length; index += 1) {
      for (let nextIndex = index + 1; nextIndex < visibleNodes.length; nextIndex += 1) {
        const first = visibleNodes[index];
        const second = visibleNodes[nextIndex];
        const firstPoint = points.get(first.id);
        const secondPoint = points.get(second.id);

        if (!firstPoint || !secondPoint) {
          continue;
        }

        const minDistance =
          first.kind === "medicine" && second.kind === "medicine"
            ? 17
            : first.kind === "medicine" || second.kind === "medicine"
              ? 11.4
              : 7.3;
        const dx = secondPoint.x - firstPoint.x;
        const dy = secondPoint.y - firstPoint.y;
        const distance = Math.max(Math.hypot(dx, dy), 0.01);

        if (distance >= minDistance) {
          continue;
        }

        const force = ((minDistance - distance) / distance) * 0.18;
        const moveX = dx * force;
        const moveY = dy * force;

        firstPoint.x -= moveX;
        firstPoint.y -= moveY;
        secondPoint.x += moveX;
        secondPoint.y += moveY;
      }
    }

    for (const node of visibleNodes) {
      const point = points.get(node.id);

      if (!point) {
        continue;
      }

      const minX = node.kind === "medicine" ? 24 : 7;
      const maxX = node.kind === "medicine" ? 76 : 93;
      const minY = node.kind === "medicine" ? 23 : 8;
      const maxY = node.kind === "medicine" ? 77 : 92;

      point.x = Math.min(maxX, Math.max(minX, point.x));
      point.y = Math.min(maxY, Math.max(minY, point.y));
    }
  }

  removeNodeOverlaps(points, visibleNodes, "overview");

  return points;
}

function buildFocusedLayout(nodes: GraphNode[]) {
  const points = new Map(
    nodes.map((node) => [node.id, node.detail ? { ...node.detail } : { ...node.overview }]),
  );

  removeNodeOverlaps(points, nodes, "focused");

  return points;
}

function readUrlGraphMode(): GraphMode {
  if (typeof window === "undefined") {
    return "overview";
  }

  return new URLSearchParams(window.location.search).get("medicine") === selectedMedicineSlug
    ? "focused"
    : "overview";
}

function writeUrlGraphMode(
  mode: GraphMode,
  historyMethod: "pushState" | "replaceState" = "pushState",
) {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(window.location.href);

  if (mode === "focused") {
    url.searchParams.set("medicine", selectedMedicineSlug);
  } else {
    url.searchParams.delete("medicine");
  }

  const nextUrl = `${url.pathname}${url.search}${url.hash}`;
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;

  if (nextUrl === currentUrl) {
    return;
  }

  window.history[historyMethod]({ sanitasGraphMode: mode }, "", nextUrl);
}

export function Dashboard() {
  const [viewMode, setViewMode] = useState<ViewMode>("overview");
  const [selectedNodeId, setSelectedNodeId] = useState(selectedMedicineId);
  const [panelNodeId, setPanelNodeId] = useState(selectedMedicineId);
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [investigationState, setInvestigationState] = useState<"idle" | "running" | "complete">(
    "idle",
  );
  const [addedEvidence, setAddedEvidence] = useState(false);
  const [pulsePath, setPulsePath] = useState(false);
  const [insertingNodeId, setInsertingNodeId] = useState<string | null>(null);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [streamSteps, setStreamSteps] = useState<InvestigationStreamStep[]>(
    createInitialInvestigationSteps,
  );
  const streamAbortRef = useRef<AbortController | null>(null);
  const commandInputRef = useRef<HTMLInputElement>(null);
  const notificationsRef = useRef<HTMLDivElement>(null);
  const searchButtonRef = useRef<HTMLButtonElement>(null);
  const graphMode: GraphMode = viewMode === "overview" ? "overview" : "focused";

  const activePath = useMemo(() => new Set(riskPathBase), []);
  const selectedNode = graphNodes.find((node) => node.id === selectedNodeId) ?? graphNodes[0];
  const panelNode = graphNodes.find((node) => node.id === panelNodeId) ?? selectedNode;
  const selectedDetails = detailsForNode(panelNode);
  const evidenceCount = addedEvidence ? 5 : 4;
  const confidence = addedEvidence ? "92%" : "88%";
  const sidebarOpen =
    viewMode === "node-detail" || viewMode === "investigating" || viewMode === "report-ready";

  const openCommandPalette = () => {
    setNotificationsOpen(false);
    setCommandPaletteOpen(true);
  };

  const showOverview = () => {
    setNotificationsOpen(false);
    setViewMode("overview");
    setSelectedNodeId(selectedMedicineId);
    setPanelNodeId(selectedMedicineId);
    setExpandedNodeId(null);
    writeUrlGraphMode("overview");
  };

  const closeCommandPalette = () => {
    setCommandPaletteOpen(false);
    setCommandQuery("");
    window.requestAnimationFrame(() => searchButtonRef.current?.focus());
  };

  useEffect(
    () => () => {
      streamAbortRef.current?.abort();
    },
    [],
  );

  useEffect(() => {
    const syncFromUrl = () => {
      const nextMode = readUrlGraphMode();

      setViewMode(nextMode === "overview" ? "overview" : "medicine-focus");
      setSelectedNodeId(selectedMedicineId);
      setPanelNodeId(selectedMedicineId);
      setExpandedNodeId(null);
    };

    syncFromUrl();
    window.addEventListener("popstate", syncFromUrl);

    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (commandPaletteOpen && event.key === "Escape") {
        event.preventDefault();
        closeCommandPalette();
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (commandPaletteOpen) {
          closeCommandPalette();
          return;
        }

        openCommandPalette();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [commandPaletteOpen]);

  useEffect(() => {
    if (!notificationsOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (
        notificationsRef.current &&
        event.target instanceof Node &&
        !notificationsRef.current.contains(event.target)
      ) {
        setNotificationsOpen(false);
      }
    };

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setNotificationsOpen(false);
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [notificationsOpen]);

  useEffect(() => {
    if (!commandPaletteOpen) {
      return;
    }

    window.requestAnimationFrame(() => commandInputRef.current?.focus());
  }, [commandPaletteOpen]);

  const focusMedicine = () => {
    setViewMode("medicine-focus");
    setSelectedNodeId(selectedMedicineId);
    setPanelNodeId(selectedMedicineId);
    setExpandedNodeId(null);
    writeUrlGraphMode("focused");
  };

  const handleAgentStreamPart = (part: AgentStreamPart) => {
    if (part.type === "data-agent-step") {
      setStreamSteps((currentSteps) =>
        currentSteps.map((step) =>
          step.id === part.data.id
            ? {
                ...step,
                label: part.data.label,
                status: part.data.status,
                summary: part.data.summary ?? step.summary,
                toolCount: part.data.toolCount,
              }
            : step,
        ),
      );
      return;
    }

    if (part.type === "data-agent-tool") {
      setStreamSteps((currentSteps) =>
        currentSteps.map((step) =>
          step.id === part.data.stepId
            ? {
                ...step,
                tools: step.tools.map((tool) =>
                  tool.id === part.data.id
                    ? {
                        ...tool,
                        label: part.data.label,
                        outputSummary: part.data.outputSummary ?? tool.outputSummary,
                        status: part.data.status,
                        toolName: part.data.toolName,
                      }
                    : tool,
                ),
              }
            : step,
        ),
      );
      return;
    }

    if (part.type === "data-agent-reasoning") {
      setStreamSteps((currentSteps) =>
        currentSteps.map((step) => {
          if (step.id !== part.data.stepId) {
            return step;
          }

          const existingReasoning = step.reasoning.find((item) => item.id === part.data.id);
          const nextReasoning: InvestigationReasoningSummary = {
            afterToolId: part.data.afterToolId,
            beforeToolId: part.data.beforeToolId,
            id: part.data.id,
            status: part.data.status,
            text: part.data.text,
          };

          return {
            ...step,
            reasoning: existingReasoning
              ? step.reasoning.map((item) =>
                  item.id === part.data.id ? { ...item, ...nextReasoning } : item,
                )
              : [...step.reasoning, nextReasoning],
          };
        }),
      );
      return;
    }

    if (part.type === "data-graph-update") {
      const insertedNodeId = part.data.addedEvidenceNodeIds.at(-1) ?? scriptedSourceId;

      setAddedEvidence(true);
      setPulsePath(true);
      setSelectedNodeId(insertedNodeId);
      setPanelNodeId(insertedNodeId);
      setExpandedNodeId(insertedNodeId);
      setInsertingNodeId(insertedNodeId);
      window.setTimeout(() => setPulsePath(false), 1300);
      window.setTimeout(() => setInsertingNodeId(null), 2600);
      return;
    }

    if (part.type === "data-report-ready") {
      setInvestigationState("complete");
      setViewMode("report-ready");
      setPulsePath(true);
      window.setTimeout(() => setPulsePath(false), 1300);
    }
  };

  const startInvestigation = () => {
    if (investigationState === "running") {
      return;
    }

    setNotificationsOpen(false);
    streamAbortRef.current?.abort();
    setAddedEvidence(false);
    setInsertingNodeId(null);
    setStreamSteps(createInitialInvestigationSteps());
    setViewMode("investigating");
    setSelectedNodeId("event-fda-shortage");
    setPanelNodeId("event-fda-shortage");
    setExpandedNodeId(null);
    setInvestigationState("running");
    writeUrlGraphMode("focused");

    const abortController = new AbortController();
    streamAbortRef.current = abortController;

    void fetch("/api/agent", {
      body: JSON.stringify({
        messages: [],
        scenario: carboplatinDemoScenario,
        selectedNodeId: "event-fda-shortage",
      }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          throw new Error("Agent stream failed to start.");
        }

        await readAgentEventStream(response.body, handleAgentStreamPart);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setInvestigationState("idle");
      });
  };

  const selectCommandNode = (node: GraphNode) => {
    setNotificationsOpen(false);

    if (node.id === selectedMedicineId) {
      focusMedicine();
      return;
    }

    setSelectedNodeId(node.id);
    setPanelNodeId(node.id);
    setExpandedNodeId(null);
    setViewMode("node-detail");
    writeUrlGraphMode("focused");
  };

  const openEvidenceNode = () => {
    setNotificationsOpen(false);
    setSelectedNodeId("event-fda-shortage");
    setPanelNodeId("event-fda-shortage");
    setExpandedNodeId(null);
    setViewMode("node-detail");
    writeUrlGraphMode("focused");
  };

  const openAddedSourceNode = () => {
    if (!addedEvidence) {
      return;
    }

    setNotificationsOpen(false);
    setSelectedNodeId(scriptedSourceId);
    setPanelNodeId(scriptedSourceId);
    setExpandedNodeId(null);
    setViewMode("node-detail");
    writeUrlGraphMode("focused");
  };

  const commandItems: CommandPaletteItem[] = [
    {
      action: showOverview,
      icon: <Waves aria-hidden size={15} />,
      id: "show-network",
      meta: "Return to the full medicine network",
      title: "Show network",
      token: "overview network all medicines",
    },
    {
      action: startInvestigation,
      icon: <FileSearch aria-hidden size={15} />,
      id: "investigate-evidence",
      meta: "Search newer sources and update the risk path",
      title: "Investigate evidence",
      token: "investigate evidence sources latest search",
    },
    ...graphNodes
      .filter((node) => node.id !== scriptedSourceId || addedEvidence)
      .map((node) => ({
        action: () => selectCommandNode(node),
        icon: kindIcons[node.kind],
        id: node.id,
        meta: `${node.kind}: ${node.summary}`,
        title: node.label,
        token: `${node.label} ${node.kind} ${node.summary} ${node.metric ?? ""}`,
      })),
  ];

  return (
    <main className={cn("medicine-graph-screen", `is-${graphMode}`, `view-${viewMode}`)}>
      <nav className="medicine-graph-nav" aria-label="Medicine graph controls">
        <button className="medicine-graph-brand" type="button" onClick={showOverview}>
          <img
            alt=""
            aria-hidden
            className="sanitas-logo-mark"
            src="/logo-candidates/sanitas-logo-5-compact-bottle-transparent.png"
          />
          <strong>Sanitas</strong>
        </button>

        <button
          className="medicine-graph-search"
          ref={searchButtonRef}
          type="button"
          onClick={openCommandPalette}
        >
          <Search aria-hidden size={15} />
          <span>
            {viewMode === "overview" ? "Find medicine, supplier, source" : selectedNode.label}
          </span>
          <kbd>⌘K</kbd>
        </button>

        <div className="medicine-graph-nav-actions">
          <span
            className={cn("medicine-graph-risk-pill", graphMode === "focused" && "is-critical")}
          >
            <ShieldAlert aria-hidden size={15} />
            {viewMode === "overview" ? "7 mapped medicines" : "87 action path"}
          </span>
          <div className="notification-anchor" ref={notificationsRef}>
            <button
              aria-expanded={notificationsOpen}
              aria-label="Graph Change Timeline"
              className="medicine-graph-alert"
              type="button"
              onClick={() => {
                setCommandPaletteOpen(false);
                setNotificationsOpen((isOpen) => !isOpen);
              }}
            >
              <Bell aria-hidden size={16} />
              <span>{addedEvidence ? 5 : 4}</span>
            </button>
            {notificationsOpen ? (
              <GraphNotifications
                addedEvidence={addedEvidence}
                investigationState={investigationState}
                onOpenAddedSource={openAddedSourceNode}
                onOpenEvidence={openEvidenceNode}
                onStartInvestigation={startInvestigation}
              />
            ) : null}
          </div>
        </div>
      </nav>

      <section className="medicine-graph-stage" aria-label="Medicine Risk Network">
        <MedicineRiskGraph
          activePath={activePath}
          addedEvidence={addedEvidence}
          expandedNodeId={expandedNodeId}
          hoveredNodeId={hoveredNodeId}
          insertingNodeId={insertingNodeId}
          mode={graphMode}
          pulsePath={pulsePath}
          selectedNodeId={selectedNode.id}
          onFocusMedicine={focusMedicine}
          onHoverNode={setHoveredNodeId}
          onExpandNode={setExpandedNodeId}
          onSelectNode={(node) => {
            if (node.id === scriptedSourceId && addedEvidence) {
              const sourceUrl = sourceUrlForNode(node.id);

              if (sourceUrl) {
                window.open(sourceUrl, "_blank", "noopener,noreferrer");
                return;
              }
            }

            if (node.kind === "medicine" && node.id === selectedMedicineId) {
              focusMedicine();
              return;
            }

            setSelectedNodeId(node.id);
            setPanelNodeId(node.id);
            setExpandedNodeId(null);
            setViewMode("node-detail");
            writeUrlGraphMode("focused");
          }}
        />
      </section>

      {sidebarOpen ? (
        <RiskSidePanel
          key={`${viewMode}-${panelNode.id}`}
          addedEvidence={addedEvidence}
          confidence={confidence}
          details={selectedDetails}
          evidenceCount={evidenceCount}
          investigationState={investigationState}
          highlightedNodeId={selectedNode.id}
          node={panelNode}
          onBackToOverview={showOverview}
          onSelectNode={(node) => {
            setSelectedNodeId(node.id);
            setPanelNodeId(node.id);
            setExpandedNodeId(null);
            setViewMode("node-detail");
            writeUrlGraphMode("focused");
          }}
          onSelectSourceNode={(node) => {
            setSelectedNodeId(node.id);
            setExpandedNodeId(null);
            setViewMode("node-detail");
            writeUrlGraphMode("focused");
          }}
          onStartInvestigation={startInvestigation}
          streamSteps={streamSteps}
          viewMode={viewMode}
        />
      ) : null}

      <CommandPalette
        inputRef={commandInputRef}
        isOpen={commandPaletteOpen}
        items={commandItems}
        query={commandQuery}
        onClose={closeCommandPalette}
        onQueryChange={setCommandQuery}
      />
    </main>
  );
}

function GraphNotifications({
  addedEvidence,
  investigationState,
  onOpenAddedSource,
  onOpenEvidence,
  onStartInvestigation,
}: {
  addedEvidence: boolean;
  investigationState: "complete" | "idle" | "running";
  onOpenAddedSource: () => void;
  onOpenEvidence: () => void;
  onStartInvestigation: () => void;
}) {
  return (
    <div className="graph-notification-popover" role="dialog" aria-label="Graph change timeline">
      <div className="graph-notification-head">
        <span>
          <Bell aria-hidden size={14} />
          Graph changes
        </span>
        <strong>{addedEvidence ? "5 updates" : "4 updates"}</strong>
      </div>

      <div className="timeline-list graph-notification-list">
        <TimelineItem
          icon={<Activity aria-hidden size={14} />}
          text="Risk path opened for Cisplatin Injection"
        />
        <TimelineItem
          icon={<RouteIcon aria-hidden size={14} />}
          text="Supplier chain anchored to FDA shortage evidence"
        />
        {investigationState === "running" ? (
          <TimelineItem
            icon={<Loader2 aria-hidden size={14} />}
            isRunning
            text="AI investigation is updating the graph"
          />
        ) : null}
        {addedEvidence ? (
          <TimelineItem
            icon={<CheckCircle2 aria-hidden size={14} />}
            text="Added Times of India API report evidence"
          />
        ) : (
          <TimelineItem
            icon={<FileSearch aria-hidden size={14} />}
            text="One newer public source is ready to investigate"
          />
        )}
      </div>

      <div className="graph-notification-actions">
        <button type="button" onClick={onOpenEvidence}>
          <FileText aria-hidden size={14} />
          FDA evidence
        </button>
        {addedEvidence ? (
          <button type="button" onClick={onOpenAddedSource}>
            <ExternalLink aria-hidden size={14} />
            New source
          </button>
        ) : (
          <button
            type="button"
            disabled={investigationState === "running"}
            onClick={onStartInvestigation}
          >
            <Sparkles aria-hidden size={14} />
            Investigate
          </button>
        )}
      </div>
    </div>
  );
}

function CommandPalette({
  inputRef,
  isOpen,
  items,
  onClose,
  onQueryChange,
  query,
}: {
  inputRef: React.RefObject<HTMLInputElement | null>;
  isOpen: boolean;
  items: CommandPaletteItem[];
  onClose: () => void;
  onQueryChange: (query: string) => void;
  query: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredItems = normalizedQuery
    ? items.filter((item) => item.token.toLowerCase().includes(normalizedQuery))
    : items;

  useEffect(() => {
    setActiveIndex(0);
  }, [query, isOpen]);

  if (!isOpen) {
    return null;
  }

  const runItem = (item: CommandPaletteItem) => {
    item.action();
    onClose();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!filteredItems.length) {
        return;
      }
      setActiveIndex((index) => Math.min(index + 1, filteredItems.length - 1));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!filteredItems.length) {
        return;
      }
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }

    if (event.key === "Enter" && filteredItems[activeIndex]) {
      event.preventDefault();
      runItem(filteredItems[activeIndex]);
      return;
    }

    if (event.key !== "Tab") {
      return;
    }

    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(
        'button, input, [href], [tabindex]:not([tabindex="-1"])',
      ) ?? [],
    ).filter((element) => !element.hasAttribute("disabled"));

    const first = focusable[0];
    const last = focusable.at(-1);

    if (!first || !last) {
      return;
    }

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="command-palette-backdrop" onMouseDown={onClose}>
      <div
        aria-label="Command palette"
        aria-modal="true"
        className="command-palette"
        onKeyDown={handleKeyDown}
        onMouseDown={(event) => event.stopPropagation()}
        ref={dialogRef}
        role="dialog"
      >
        <div className="command-palette-search">
          <Search aria-hidden size={17} />
          <input
            aria-label="Search medicines, suppliers, sources, and commands"
            placeholder="Search graph"
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
          <kbd>Esc</kbd>
        </div>

        <div className="command-palette-results" role="listbox">
          {filteredItems.length ? (
            filteredItems.map((item, index) => (
              <button
                aria-selected={index === activeIndex}
                className={cn(index === activeIndex && "is-active")}
                key={item.id}
                role="option"
                type="button"
                onClick={() => runItem(item)}
                onMouseEnter={() => setActiveIndex(index)}
              >
                <span className="command-palette-item-icon">{item.icon}</span>
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.meta}</small>
                </span>
              </button>
            ))
          ) : (
            <p className="command-palette-empty">No graph matches</p>
          )}
        </div>
      </div>
    </div>
  );
}

function MedicineRiskGraph({
  activePath,
  addedEvidence,
  expandedNodeId,
  hoveredNodeId,
  insertingNodeId,
  mode,
  onExpandNode,
  onFocusMedicine,
  onHoverNode,
  onSelectNode,
  pulsePath,
  selectedNodeId,
}: {
  activePath: Set<string>;
  addedEvidence: boolean;
  expandedNodeId: string | null;
  hoveredNodeId: string | null;
  insertingNodeId: string | null;
  mode: GraphMode;
  onExpandNode: (id: string | null) => void;
  onFocusMedicine: () => void;
  onHoverNode: (id: string | null) => void;
  onSelectNode: (node: GraphNode) => void;
  pulsePath: boolean;
  selectedNodeId: string;
}) {
  const focusEdgeIds = new Set(
    (medicineSupplyChainEdges[selectedMedicineId] ?? []).filter(
      (edgeId) => edgeId !== "e-api-times-india-source",
    ),
  );

  if (addedEvidence) {
    focusEdgeIds.add("e-shortage-times-india-evidence");
  }

  const focusNodeIds = new Set<string>([selectedMedicineId, selectedNodeId]);
  const visibleEdges =
    mode === "overview"
      ? graphEdges.filter((edge) => !edge.scripted || addedEvidence)
      : graphEdges.filter((edge) => {
          if (edge.scripted && !addedEvidence) {
            return false;
          }

          return focusEdgeIds.has(edge.id);
        });

  for (const edge of visibleEdges) {
    focusNodeIds.add(edge.from);
    focusNodeIds.add(edge.to);
  }

  const visibleNodes = graphNodes
    .filter((node) => node.id !== scriptedSourceId || addedEvidence)
    .filter((node) => mode === "overview" || focusNodeIds.has(node.id));
  const byId = new Map(visibleNodes.map((node) => [node.id, node]));
  const drawableEdges = visibleEdges.filter((edge) => byId.has(edge.from) && byId.has(edge.to));
  const hoveredNode = hoveredNodeId ? byId.get(hoveredNodeId) : null;
  const overviewLayout = buildOverviewLayout(visibleNodes);
  const focusedLayout = buildFocusedLayout(visibleNodes);
  const hoveredMedicineId = hoveredNode?.kind === "medicine" ? hoveredNode.id : null;
  const hoveredMedicineEdgeIds = hoveredMedicineId
    ? new Set(medicineSupplyChainEdges[hoveredMedicineId] ?? [])
    : null;
  const hoveredMedicineNodeIds = new Set<string>();
  const hoveredEdgeIds = new Set<string>();
  const hoveredNodeIds = new Set<string>();
  const actionEdgeIds = new Set(
    graphEdges.filter((edge) => edge.actionPath).map((edge) => edge.id),
  );

  if (hoveredNode) {
    hoveredNodeIds.add(hoveredNode.id);

    for (const edge of drawableEdges) {
      if (edge.from !== hoveredNode.id && edge.to !== hoveredNode.id) {
        continue;
      }

      hoveredEdgeIds.add(edge.id);
      hoveredNodeIds.add(edge.from);
      hoveredNodeIds.add(edge.to);
    }
  }

  if (hoveredMedicineId && hoveredMedicineEdgeIds) {
    hoveredMedicineNodeIds.add(hoveredMedicineId);

    for (const edge of drawableEdges) {
      if (!hoveredMedicineEdgeIds.has(edge.id)) {
        continue;
      }

      hoveredMedicineNodeIds.add(edge.from);
      hoveredMedicineNodeIds.add(edge.to);
    }
  }

  const pointFor = (node: GraphNode) =>
    mode === "focused"
      ? (focusedLayout.get(node.id) ?? node.detail ?? node.overview)
      : (overviewLayout.get(node.id) ?? node.overview);
  const pathFor = (edge: GraphEdge, index: number) => {
    const from = byId.get(edge.from);
    const to = byId.get(edge.to);

    if (!from || !to) {
      return "";
    }

    const fromPoint = pointFor(from);
    const toPoint = pointFor(to);
    const midX = (fromPoint.x + toPoint.x) / 2;

    if (mode === "overview") {
      return `M ${fromPoint.x} ${fromPoint.y} L ${toPoint.x} ${toPoint.y}`;
    }

    const isEvidenceEdge = from.kind === "source" || to.kind === "source";
    const controlOffset = isEvidenceEdge ? 5.8 + (index % 4) * 0.85 : 3.2;

    return `M ${fromPoint.x} ${fromPoint.y} C ${midX} ${fromPoint.y - controlOffset}, ${midX} ${
      toPoint.y + controlOffset
    }, ${toPoint.x} ${toPoint.y}`;
  };

  return (
    <div
      className={cn(
        "medicine-risk-graph",
        `is-${mode}`,
        pulsePath && "is-pulsing",
        Boolean(hoveredNode) && "has-node-hover",
        Boolean(hoveredMedicineId) && "has-medicine-hover",
      )}
    >
      <svg
        aria-hidden
        className="medicine-risk-links"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="sanitas-critical-link" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="oklch(0.7 0.19 28)" stopOpacity="0.24" />
            <stop offset="100%" stopColor="oklch(0.64 0.23 25)" stopOpacity="0.92" />
          </linearGradient>
          <linearGradient id="sanitas-calm-link" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="oklch(0.72 0.02 190)" stopOpacity="0.1" />
            <stop offset="100%" stopColor="oklch(0.82 0.03 180)" stopOpacity="0.34" />
          </linearGradient>
        </defs>
        {drawableEdges.map((edge, index) => {
          const isActive = Boolean(edge.actionPath);
          const isActionEdge = actionEdgeIds.has(edge.id);
          const isHoveredEdge = hoveredEdgeIds.has(edge.id);
          const isHoveredMedicineEdge = Boolean(hoveredMedicineEdgeIds?.has(edge.id));
          const fromNode = byId.get(edge.from);
          const toNode = byId.get(edge.to);
          const isEvidenceEdge = fromNode?.kind === "source" || toNode?.kind === "source";
          const edgeStyle = riskStyleFor(edge, {
            "--link-delay": `${Math.min(index * 6, 160)}ms`,
          } as CSSProperties);

          return (
            <path
              className={cn(
                "medicine-risk-link",
                `risk-${edge.risk}`,
                isActive && "is-active",
                isActionEdge && "is-critical-chain",
                isEvidenceEdge && "is-evidence-link",
                (isHoveredEdge || isHoveredMedicineEdge) && "is-hover-trace",
                Boolean(
                  hoveredNode &&
                  !isHoveredEdge &&
                  (!hoveredMedicineEdgeIds || !isHoveredMedicineEdge),
                ) && "is-hover-muted",
                edge.scripted && "is-scripted",
              )}
              d={pathFor(edge, index)}
              key={edge.id}
              style={edgeStyle}
            />
          );
        })}
      </svg>

      {visibleNodes.map((node, index) => {
        const point = pointFor(node);
        const isActive = activePath.has(node.id);
        const isDimmed = mode === "focused" && !isActive && !node.actionPath;
        const isSource = node.kind === "source";
        const isHoveredNode = hoveredNodeIds.has(node.id);
        const isHoveredMedicineNode = hoveredMedicineNodeIds.has(node.id);
        const isSelectedNode = selectedNodeId === node.id;
        const isOverviewMedicine = mode === "overview" && node.kind === "medicine";
        const nodeStyle = riskStyleFor(node, {
          "--node-delay": `${Math.min(index * 10, 220)}ms`,
          left: `${point.x}%`,
          top: `${point.y}%`,
        } as CSSProperties);

        return (
          <button
            aria-label={`${node.label}: ${node.summary}`}
            className={cn(
              "medicine-risk-node",
              `node-${node.kind}`,
              `risk-${node.risk}`,
              isActive && "is-active-path",
              node.actionPath && "is-action-path",
              isDimmed && "is-dimmed",
              Boolean(isHoveredNode || (hoveredMedicineId && isHoveredMedicineNode)) &&
                "is-hover-trace",
              Boolean(hoveredNode && !isHoveredNode && !isHoveredMedicineNode) && "is-hover-muted",
              isSelectedNode && !isOverviewMedicine && "is-selected",
              expandedNodeId === node.id && "is-expanded",
              insertingNodeId === node.id && "is-inserting",
              node.id === selectedMedicineId && "is-critical-medicine",
              node.id === scriptedSourceId && "is-new-evidence",
              isSource && "is-evidence-satellite",
              mode === "overview" && node.kind !== "medicine" && "is-overview-icon",
            )}
            key={`${mode}-${node.id}`}
            onClick={() => {
              onHoverNode(null);

              if (mode === "overview" && node.kind === "medicine") {
                onExpandNode(node.id);
              } else {
                onExpandNode(null);
              }

              if (node.id === selectedMedicineId) {
                onFocusMedicine();
                return;
              }

              onSelectNode(node);
            }}
            onPointerDown={() => {
              if (mode === "overview" && node.kind === "medicine") {
                onExpandNode(node.id);
              }
            }}
            onMouseEnter={() => {
              if (mode !== "overview" || node.kind === "medicine") {
                onHoverNode(node.id);
              }
            }}
            onMouseLeave={() => {
              if (mode !== "overview" || node.kind === "medicine") {
                onHoverNode(null);
              }
            }}
            style={nodeStyle}
            type="button"
          >
            <span className="node-icon">{kindIcons[node.kind]}</span>
            <strong>{node.label}</strong>
            <small>{node.riskReason ?? node.summary}</small>
            {node.metric ? <em>{node.metric}</em> : null}
          </button>
        );
      })}
    </div>
  );
}

function RiskSidePanel({
  addedEvidence,
  confidence,
  details,
  evidenceCount,
  highlightedNodeId,
  investigationState,
  node,
  onBackToOverview,
  onSelectNode,
  onSelectSourceNode,
  onStartInvestigation,
  streamSteps,
  viewMode,
}: {
  addedEvidence: boolean;
  confidence: string;
  details: NodeDetails[string];
  evidenceCount: number;
  highlightedNodeId: string;
  investigationState: "complete" | "idle" | "running";
  node: GraphNode;
  onBackToOverview: () => void;
  onSelectNode: (node: GraphNode) => void;
  onSelectSourceNode: (node: GraphNode) => void;
  onStartInvestigation: () => void;
  streamSteps: InvestigationStreamStep[];
  viewMode: ViewMode;
}) {
  const isSource = node.kind === "source";
  const primarySource = details.sources[0];
  const visualEvidence = details.sources.slice(0, 3);
  const actionPathNodes = supplierRiskPath
    .map((nodeId) => graphNodes.find((candidate) => candidate.id === nodeId))
    .filter((candidate): candidate is GraphNode => Boolean(candidate));
  const shortageEvidenceNode = graphNodes.find(
    (candidate) => candidate.id === "event-fda-shortage",
  );
  const panelFinding =
    node.id === "event-fda-shortage"
      ? "Active shortage signal with supplier-level constraints."
      : node.id === "event-gmp"
        ? "Quality compliance is the clearest supplier constraint."
        : node.id === "supplier-accord-intas"
          ? "This supplier path carries the strongest action signal."
          : node.kind === "source"
            ? "Evidence supporting the mapped cisplatin risk path."
            : (node.riskReason ?? details.whyItMatters);

  if (viewMode === "investigating" || viewMode === "report-ready") {
    return (
      <InvestigationPanel
        addedEvidence={addedEvidence}
        investigationState={investigationState}
        onBackToOverview={onBackToOverview}
        streamSteps={streamSteps}
        viewMode={viewMode}
      />
    );
  }

  return (
    <aside className="risk-side-panel" aria-label="Risk Profile and node investigation">
      <div className="risk-panel-head">
        <button type="button" onClick={onBackToOverview}>
          <ChevronLeft aria-hidden size={15} />
          Network
        </button>
        <span>Node evidence</span>
      </div>

      <section className="visual-risk-card">
        <div className="visual-risk-hero">
          <span className={cn("risk-orb", `risk-${node.risk}`)}>{riskScoreFor(node)}</span>
          <div>
            <p>{node.kind === "source" ? "Evidence" : "Supply Risk"}</p>
            <h1>{node.label}</h1>
            <strong>{panelFinding}</strong>
          </div>
        </div>

        <div className="visual-stat-row" aria-label="Risk evidence summary">
          <span>
            <ShieldAlert aria-hidden size={14} />
            {node.id === selectedMedicineId ? confidence : details.confidence}
          </span>
          <span>
            <FileText aria-hidden size={14} />
            {node.id === selectedMedicineId ? evidenceCount : details.sources.length} sources
          </span>
        </div>
      </section>

      <section className="visual-path-card" aria-label="Highlighted risk path">
        <h2>Risk path</h2>
        {actionPathNodes.map((pathNode, index) => (
          <button
            className={cn(pathNode.id === node.id && "is-current")}
            key={pathNode.id}
            type="button"
            onClick={() => onSelectNode(pathNode)}
          >
            <span>{index + 1}</span>
            <strong>{pathNode.label}</strong>
          </button>
        ))}
        {shortageEvidenceNode ? (
          <button
            className={cn(
              "visual-path-evidence",
              shortageEvidenceNode.id === node.id && "is-current",
            )}
            type="button"
            onClick={() => onSelectNode(shortageEvidenceNode)}
          >
            <span>
              <FileText aria-hidden size={13} />
            </span>
            <div>
              <small>Evidence status</small>
              <strong>{shortageEvidenceNode.label}</strong>
            </div>
          </button>
        ) : null}
      </section>

      <section className="visual-evidence-card" aria-label="Mapped evidence">
        <h2>Evidence</h2>
        <div className="visual-evidence-strip">
          {visualEvidence.map((source) => {
            const sourceNode = findSourceNodeForEvidence(source);

            return (
              <button
                className={cn(sourceNode?.id === highlightedNodeId && "is-current")}
                disabled={!sourceNode}
                key={source.title}
                type="button"
                onClick={() => {
                  if (sourceNode) {
                    onSelectSourceNode(sourceNode);
                  }
                }}
              >
                <FileText aria-hidden size={15} />
                <strong>{source.title}</strong>
              </button>
            );
          })}
        </div>
      </section>

      <section className="visual-impact-card">
        <div>
          <Activity aria-hidden size={18} />
          <strong>Oncology availability risk</strong>
        </div>
        <p>Delays can force allocation, substitution, or treatment timing decisions.</p>
      </section>

      <section className="visual-action-card">
        <div>
          <strong>Investigate supplier readiness</strong>
          <p>Check approved alternatives and lead times before stock drops below threshold.</p>
        </div>
        <button type="button" onClick={onStartInvestigation}>
          <Sparkles aria-hidden size={15} />
          Investigate
        </button>
        {isSource && primarySource ? (
          <a
            className="open-source-action"
            href={primarySource.url}
            rel="noreferrer"
            target="_blank"
          >
            Open source <ExternalLink aria-hidden size={14} />
          </a>
        ) : null}
      </section>
    </aside>
  );
}

function InvestigationPanel({
  addedEvidence,
  investigationState,
  onBackToOverview,
  streamSteps,
  viewMode,
}: {
  addedEvidence: boolean;
  investigationState: "complete" | "idle" | "running";
  onBackToOverview: () => void;
  streamSteps: InvestigationStreamStep[];
  viewMode: ViewMode;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const isReportReady = viewMode === "report-ready";
  const replayState = getCarboplatinDemoReplayState(
    isReportReady ? "report-ready" : investigationState === "running" ? "running" : "idle",
  );

  useEffect(() => {
    if (investigationState !== "running") {
      return;
    }

    const panel = panelRef.current;
    if (!panel) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const activeStep = panel.querySelector<HTMLElement>(".step-call-item.is-running");
      if (!activeStep) {
        return;
      }

      const panelRect = panel.getBoundingClientRect();
      const stepRect = activeStep.getBoundingClientRect();
      const bottomMargin = Math.min(180, Math.max(112, panel.clientHeight * 0.18));
      const desiredStepBottom = panelRect.bottom - bottomMargin;
      const delta = stepRect.bottom - desiredStepBottom;

      panel.scrollTo({
        behavior: "smooth",
        top: panel.scrollTop + delta,
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [investigationState, streamSteps]);

  return (
    <aside
      className={cn("risk-side-panel", "investigation-panel", isReportReady && "is-report-ready")}
      aria-label="AI graph investigation"
      ref={panelRef}
    >
      <div className="risk-panel-head">
        <button type="button" onClick={onBackToOverview}>
          <ChevronLeft aria-hidden size={15} />
          Network
        </button>
        <span>{isReportReady ? "Report context ready" : "AI investigation"}</span>
      </div>

      <section className="risk-profile-block investigation-brief">
        <div className="risk-profile-title">
          <span className={cn("risk-dot", isReportReady ? "risk-watch" : "risk-critical")} />
          <div>
            <p>Graph Intelligence</p>
            <h1>{isReportReady ? "Report context prepared" : "Investigating action path"}</h1>
          </div>
        </div>
        <p className="risk-panel-copy">
          {isReportReady
            ? "Evidence, risk path, and recommended action are ready for the hospital report module."
            : "The agent is gathering mapped context, searching for one newer source, and preparing a graph update."}
        </p>
      </section>

      <section className="risk-panel-section">
        <h2>Steps</h2>
        <div className="step-call-list">
          {streamSteps.map((step) => {
            const isDone = step.status === "complete";
            const isRunning = step.status === "running";
            const visibleTools = isRunning
              ? step.tools
              : step.tools.filter((tool) => tool.status === "complete");
            const visibleReasoningIds = new Set(
              (isRunning ? step.reasoning.slice(-4) : []).map((reasoning) => reasoning.id),
            );
            const standaloneReasoning = isRunning
              ? step.reasoning.filter(
                  (item) =>
                    visibleReasoningIds.has(item.id) && !item.beforeToolId && !item.afterToolId,
                )
              : [];
            const reasoningBeforeTool = (toolId: string) =>
              isRunning
                ? step.reasoning.filter(
                    (item) => visibleReasoningIds.has(item.id) && item.beforeToolId === toolId,
                  )
                : [];
            const reasoningAfterTool = (toolId: string) =>
              isRunning
                ? step.reasoning.filter(
                    (item) => visibleReasoningIds.has(item.id) && item.afterToolId === toolId,
                  )
                : [];

            return (
              <article
                className={cn("step-call-item", isDone && "is-done", isRunning && "is-running")}
                key={step.id}
                data-step-id={step.id}
              >
                <div className="step-call-head">
                  <span>
                    {isDone ? (
                      <CheckCircle2 aria-hidden size={14} />
                    ) : isRunning ? (
                      <Loader2 aria-hidden size={14} />
                    ) : (
                      <Bot aria-hidden size={14} />
                    )}
                  </span>
                  <div>
                    <strong>
                      {iconForStep(step.id)}
                      {step.label}
                    </strong>
                    <p>
                      {isDone
                        ? `${step.toolCount} tools completed`
                        : isRunning
                          ? runningStepCopy(step.id)
                          : `${step.toolCount} tools queued`}
                    </p>
                  </div>
                </div>
                {isDone && step.summary ? (
                  <p className="step-call-summary">{step.summary}</p>
                ) : null}
                {visibleTools.length > 0 ? (
                  <div className="step-tool-list">
                    {standaloneReasoning.map((reasoning) => (
                      <StepReasoningItem key={reasoning.id} reasoning={reasoning} />
                    ))}
                    {visibleTools.flatMap((tool) => [
                      ...reasoningBeforeTool(tool.id).map((reasoning) => (
                        <StepReasoningItem key={reasoning.id} reasoning={reasoning} />
                      )),
                      <div
                        className={cn(
                          "step-tool-item",
                          tool.status === "complete" && "is-done",
                          tool.status === "running" && "is-running",
                        )}
                        key={tool.id}
                      >
                        {tool.status === "complete" ? (
                          <CheckCircle2 aria-hidden size={12} />
                        ) : tool.status === "running" ? (
                          <Loader2 aria-hidden size={12} />
                        ) : (
                          <Bot aria-hidden size={12} />
                        )}
                        <div>
                          <strong>{tool.label}</strong>
                          <span>{tool.outputSummary ?? tool.toolName}</span>
                        </div>
                      </div>,
                      ...reasoningAfterTool(tool.id).map((reasoning) => (
                        <StepReasoningItem key={reasoning.id} reasoning={reasoning} />
                      )),
                    ])}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>

      {isReportReady ? (
        <section className="risk-panel-section">
          <h2>Report Preview</h2>
          <ReportPreview />
        </section>
      ) : null}

      {addedEvidence && !isReportReady ? (
        <section className="risk-panel-section new-source-card">
          <h2>Inserted Evidence Node</h2>
          <article>
            <FileText aria-hidden size={15} />
            <div>
              <strong>{replayState.source.title}</strong>
              <span>
                {replayState.source.publisher} · {replayState.source.mode}
              </span>
            </div>
            <a href={replayState.source.url} rel="noreferrer" target="_blank">
              Open <ExternalLink aria-hidden size={13} />
            </a>
          </article>
        </section>
      ) : null}

      <InvestigationTimeline
        addedEvidence={addedEvidence}
        investigationState={investigationState}
      />
    </aside>
  );
}

function StepReasoningItem({ reasoning }: { reasoning: InvestigationReasoningSummary }) {
  return (
    <div className={cn("step-reasoning-item", reasoning.status === "streaming" && "is-streaming")}>
      <Bot aria-hidden size={12} />
      <div>
        <strong>Reasoning</strong>
        <p>{reasoning.text}</p>
      </div>
    </div>
  );
}

function runningStepCopy(stepId: string) {
  const copyByStepId: Record<string, string> = {
    "map-current-evidence": "Reading current evidence anchors",
    "prepare-report": "Preparing the action handoff",
    "search-newer-sources": "Checking source credibility",
    "update-graph": "Adding the credible source node",
  };

  return copyByStepId[stepId] ?? "Running grouped tool calls";
}

function iconForStep(stepId: string) {
  const iconProps = { "aria-hidden": true, size: 13 };

  if (stepId === "map-current-evidence") {
    return <RouteIcon {...iconProps} />;
  }

  if (stepId === "search-newer-sources") {
    return <Radar {...iconProps} />;
  }

  if (stepId === "update-graph") {
    return <Workflow {...iconProps} />;
  }

  if (stepId === "prepare-report") {
    return <FileText {...iconProps} />;
  }

  return <Bot {...iconProps} />;
}

function ReportPreview() {
  const report = carboplatinReportPreview;
  const statusLabel = report.status === "action-needed" ? "Action needed" : report.status;

  return (
    <div className="report-ready-box report-preview" aria-label={report.title}>
      <div className="report-preview-header">
        <div>
          <p>{report.generatedAtLabel}</p>
          <h3>{report.title}</h3>
        </div>
        <span className={cn("report-status-pill", `is-${report.status}`)}>
          <ShieldAlert aria-hidden size={13} />
          {statusLabel}
        </span>
      </div>

      <p className="report-finding">{report.headlineFinding}</p>

      <div className="report-action-box">
        <strong>{report.recommendedAction.title}</strong>
        <p>{report.recommendedAction.summary}</p>
      </div>

      <a className="report-pdf-link" href={report.pdfUrl} target="_blank" rel="noreferrer">
        <FileText aria-hidden size={15} />
        PDF report
        <ExternalLink aria-hidden size={13} />
      </a>

      <p className="report-pdf-note">
        Includes evidence priority, Risk Path, operational checklist, confidence, and caveats.
      </p>
    </div>
  );
}

function InvestigationTimeline({
  addedEvidence,
  investigationState,
}: {
  addedEvidence: boolean;
  investigationState: "complete" | "idle" | "running";
}) {
  const runningSteps = [
    "Searching newer public sources",
    "Evaluating relevance to platinum API path",
    "Preparing graph evidence update",
  ];

  return (
    <section className="risk-panel-section timeline-section">
      <h2>Graph Change Timeline</h2>
      <div className="timeline-list">
        <TimelineItem
          icon={<Activity aria-hidden size={14} />}
          text="Risk Path opened for Cisplatin Injection"
        />
        <TimelineItem
          icon={<RouteIcon aria-hidden size={14} />}
          text="Supplier chain kept anchored to FDA evidence"
        />
        {investigationState === "running"
          ? runningSteps.map((step) => (
              <TimelineItem
                icon={<Loader2 aria-hidden size={14} />}
                isRunning
                key={step}
                text={step}
              />
            ))
          : null}
        {addedEvidence ? (
          <TimelineItem
            icon={<CheckCircle2 aria-hidden size={14} />}
            text="Added Times of India API report Evidence Satellite"
          />
        ) : null}
      </div>
    </section>
  );
}

function TimelineItem({
  icon,
  isRunning,
  text,
}: {
  icon: ReactNode;
  isRunning?: boolean;
  text: string;
}) {
  return (
    <article className={cn("timeline-item", isRunning && "is-running")}>
      <span>{icon}</span>
      <p>{text}</p>
    </article>
  );
}
