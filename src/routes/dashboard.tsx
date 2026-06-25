import { createFileRoute } from "@tanstack/react-router";
import {
  Activity,
  Bell,
  Bot,
  CheckCircle2,
  ChevronLeft,
  Command,
  ExternalLink,
  Factory,
  FileSearch,
  FileText,
  FlaskConical,
  Loader2,
  MapPin,
  Pill,
  Route as RouteIcon,
  Search,
  ShieldAlert,
  Sparkles,
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
  graphEdges,
  graphNodes,
  medicineSupplyChainEdges,
  nodeDetails,
  riskPathBase,
  scriptedSourceId,
  selectedMedicineId,
  selectedMedicineSlug,
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
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [investigationState, setInvestigationState] = useState<"idle" | "running" | "complete">(
    "idle",
  );
  const [addedEvidence, setAddedEvidence] = useState(false);
  const [pulsePath, setPulsePath] = useState(false);
  const commandInputRef = useRef<HTMLInputElement>(null);
  const searchButtonRef = useRef<HTMLButtonElement>(null);
  const graphMode: GraphMode = viewMode === "overview" ? "overview" : "focused";

  const activePath = useMemo(() => new Set(riskPathBase), []);
  const selectedNode = graphNodes.find((node) => node.id === selectedNodeId) ?? graphNodes[0];
  const selectedDetails = nodeDetails[selectedNode.id] ?? nodeDetails[selectedMedicineId];
  const evidenceCount = addedEvidence ? 5 : 4;
  const confidence = addedEvidence ? "92%" : "88%";
  const sidebarOpen =
    viewMode === "node-detail" || viewMode === "investigating" || viewMode === "report-ready";

  const openCommandPalette = () => {
    setCommandPaletteOpen(true);
  };

  const showOverview = () => {
    setViewMode("overview");
    setSelectedNodeId(selectedMedicineId);
    writeUrlGraphMode("overview");
  };

  const closeCommandPalette = () => {
    setCommandPaletteOpen(false);
    setCommandQuery("");
    window.requestAnimationFrame(() => searchButtonRef.current?.focus());
  };

  useEffect(() => {
    if (investigationState !== "running") {
      return;
    }

    const finish = window.setTimeout(() => {
      setAddedEvidence(true);
      setInvestigationState("complete");
      setViewMode("report-ready");
      setPulsePath(true);
    }, 2100);
    const clearPulse = window.setTimeout(() => setPulsePath(false), 3400);

    return () => {
      window.clearTimeout(finish);
      window.clearTimeout(clearPulse);
    };
  }, [investigationState]);

  useEffect(() => {
    const syncFromUrl = () => {
      const nextMode = readUrlGraphMode();

      setViewMode(nextMode === "overview" ? "overview" : "medicine-focus");
      setSelectedNodeId(selectedMedicineId);
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
    if (!commandPaletteOpen) {
      return;
    }

    window.requestAnimationFrame(() => commandInputRef.current?.focus());
  }, [commandPaletteOpen]);

  const focusMedicine = () => {
    setViewMode("medicine-focus");
    setSelectedNodeId(selectedMedicineId);
    writeUrlGraphMode("focused");
  };

  const startInvestigation = () => {
    if (investigationState === "running") {
      return;
    }

    setViewMode("investigating");
    setSelectedNodeId("event-fda-shortage");
    setInvestigationState("running");
    writeUrlGraphMode("focused");
  };

  const selectCommandNode = (node: GraphNode) => {
    if (node.id === selectedMedicineId) {
      focusMedicine();
      return;
    }

    setSelectedNodeId(node.id);
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
          <button
            aria-label="Investigate evidence"
            className="medicine-graph-investigate"
            type="button"
            onClick={startInvestigation}
          >
            <FileSearch aria-hidden size={15} />
            <span>Investigate</span>
          </button>
          <button aria-label="Graph Change Timeline" className="medicine-graph-alert" type="button">
            <Bell aria-hidden size={16} />
            <span>{addedEvidence ? 5 : 4}</span>
          </button>
          <button
            aria-label="Open commands"
            className="medicine-graph-icon"
            type="button"
            onClick={openCommandPalette}
          >
            <Command aria-hidden size={16} />
          </button>
        </div>
      </nav>

      <section className="medicine-graph-stage" aria-label="Medicine Risk Network">
        <MedicineRiskGraph
          activePath={activePath}
          addedEvidence={addedEvidence}
          hoveredNodeId={hoveredNodeId}
          mode={graphMode}
          pulsePath={pulsePath}
          selectedNodeId={selectedNode.id}
          onFocusMedicine={focusMedicine}
          onHoverNode={setHoveredNodeId}
          onSelectNode={(node) => {
            if (node.kind === "medicine" && node.id === selectedMedicineId) {
              focusMedicine();
              return;
            }

            setSelectedNodeId(node.id);
            setViewMode("node-detail");
            writeUrlGraphMode("focused");
          }}
        />
      </section>

      {sidebarOpen ? (
        <RiskSidePanel
          key={`${viewMode}-${selectedNode.id}`}
          addedEvidence={addedEvidence}
          confidence={confidence}
          details={selectedDetails}
          evidenceCount={evidenceCount}
          investigationState={investigationState}
          node={selectedNode}
          onBackToOverview={showOverview}
          onStartInvestigation={startInvestigation}
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
  hoveredNodeId,
  mode,
  onFocusMedicine,
  onHoverNode,
  onSelectNode,
  pulsePath,
  selectedNodeId,
}: {
  activePath: Set<string>;
  addedEvidence: boolean;
  hoveredNodeId: string | null;
  mode: GraphMode;
  onFocusMedicine: () => void;
  onHoverNode: (id: string | null) => void;
  onSelectNode: (node: GraphNode) => void;
  pulsePath: boolean;
  selectedNodeId: string;
}) {
  const focusEdgeIds = new Set(medicineSupplyChainEdges[selectedMedicineId] ?? []);

  if (addedEvidence) {
    focusEdgeIds.add("e-api-shortage-signal");
    focusEdgeIds.add("e-api-shortage-times-india");
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
  const hoveredMedicineId = hoveredNode?.kind === "medicine" ? hoveredNode.id : null;
  const hoveredMedicineEdgeIds = hoveredMedicineId
    ? new Set(medicineSupplyChainEdges[hoveredMedicineId] ?? [])
    : null;
  const hoveredMedicineNodeIds = new Set<string>();
  const actionEdgeIds = new Set(
    graphEdges.filter((edge) => edge.actionPath).map((edge) => edge.id),
  );

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
    mode === "focused" && node.detail
      ? node.detail
      : (overviewLayout.get(node.id) ?? node.overview);
  const pathFor = (edge: GraphEdge) => {
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

    const controlOffset = 3.2;

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
          const isHoveredMedicineEdge = Boolean(hoveredMedicineEdgeIds?.has(edge.id));
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
                isHoveredMedicineEdge && "is-hover-trace",
                Boolean(hoveredMedicineEdgeIds && !isHoveredMedicineEdge) && "is-hover-muted",
                edge.scripted && "is-scripted",
              )}
              d={pathFor(edge)}
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
        const isHoveredMedicineNode = hoveredMedicineNodeIds.has(node.id);
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
              Boolean(hoveredMedicineId && isHoveredMedicineNode) && "is-hover-trace",
              Boolean(hoveredMedicineId && !isHoveredMedicineNode) && "is-hover-muted",
              selectedNodeId === node.id && "is-selected",
              node.id === selectedMedicineId && "is-critical-medicine",
              node.id === scriptedSourceId && "is-new-evidence",
              isSource && "is-evidence-satellite",
              mode === "overview" && node.kind !== "medicine" && "is-overview-icon",
            )}
            key={`${mode}-${node.id}`}
            onClick={() => {
              if (node.id === selectedMedicineId) {
                onFocusMedicine();
                return;
              }

              onSelectNode(node);
            }}
            onMouseEnter={() => onHoverNode(node.id)}
            onMouseLeave={() => onHoverNode(null)}
            style={nodeStyle}
            type="button"
          >
            <span className="node-icon">{kindIcons[node.kind]}</span>
            <strong>{node.label}</strong>
            <small>{node.summary}</small>
            {node.metric ? <em>{node.metric}</em> : null}
          </button>
        );
      })}

      {hoveredNode ? (
        <HoverPreview mode={mode} node={hoveredNode} point={pointFor(hoveredNode)} />
      ) : null}
    </div>
  );
}

function HoverPreview({
  mode,
  node,
  point,
}: {
  mode: GraphMode;
  node: GraphNode;
  point: { x: number; y: number };
}) {
  const score = riskScoreFor(node);

  return (
    <div
      className={cn("graph-hover-preview", `risk-${node.risk}`, mode === "focused" && "is-focused")}
      style={{
        left: `${Math.min(point.x + 2, 76)}%`,
        top: `${Math.max(point.y - 9, 12)}%`,
      }}
    >
      <span>
        {node.kind} · risk {score}
      </span>
      <strong>{node.label}</strong>
      <p>{node.riskReason ?? node.summary}</p>
    </div>
  );
}

function RiskSidePanel({
  addedEvidence,
  confidence,
  details,
  evidenceCount,
  investigationState,
  node,
  onBackToOverview,
  onStartInvestigation,
  viewMode,
}: {
  addedEvidence: boolean;
  confidence: string;
  details: NodeDetails[string];
  evidenceCount: number;
  investigationState: "complete" | "idle" | "running";
  node: GraphNode;
  onBackToOverview: () => void;
  onStartInvestigation: () => void;
  viewMode: ViewMode;
}) {
  const isSource = node.kind === "source";
  const primarySource = details.sources[0];

  if (viewMode === "investigating" || viewMode === "report-ready") {
    return (
      <InvestigationPanel
        addedEvidence={addedEvidence}
        investigationState={investigationState}
        onBackToOverview={onBackToOverview}
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

      <section className="risk-profile-block">
        <div className="risk-profile-title">
          <span className={cn("risk-dot", `risk-${node.risk}`)} />
          <div>
            <p>{node.kind === "medicine" ? "Risk Profile" : "Node Investigation"}</p>
            <h1>{node.label}</h1>
          </div>
        </div>

        <div className="risk-score-row">
          <div>
            <span>Availability risk</span>
            <strong>{riskScoreFor(node)}</strong>
          </div>
          <div>
            <span>Confidence</span>
            <strong>{node.id === selectedMedicineId ? confidence : details.confidence}</strong>
          </div>
          <div>
            <span>Evidence</span>
            <strong>
              {node.id === selectedMedicineId ? evidenceCount : details.sources.length}
            </strong>
          </div>
        </div>

        <p className="risk-panel-copy">{details.whyItMatters}</p>
      </section>

      <section className="risk-panel-section">
        <h2>Care Impact</h2>
        <p>
          Used in oncology treatment where delayed availability can force allocation, substitution,
          or treatment timing decisions.
        </p>
      </section>

      <section className="risk-panel-section">
        <h2>Recommended Action</h2>
        <div className="recommendation-box">
          <strong>Prepare alternate supplier order</strong>
          <p>
            Verify usable supplier availability, lead time, and formulary alternatives before
            oncology stock falls below safety threshold.
          </p>
        </div>
      </section>

      <section className="risk-panel-section">
        <h2>Evidence</h2>
        <div className="evidence-list">
          {details.sources.map((source) => (
            <article key={source.title}>
              <FileText aria-hidden size={15} />
              <div>
                <strong>{source.title}</strong>
                <span>{source.meta}</span>
              </div>
            </article>
          ))}
        </div>
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

      <section className="risk-panel-section">
        <h2>Facts</h2>
        <ul className="fact-list">
          {details.facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
      </section>

      <section className="risk-panel-section">
        <h2>Graph Investigation</h2>
        <div className="prompt-list">
          {details.prompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={prompt === "Find newer evidence" ? onStartInvestigation : undefined}
            >
              <Sparkles aria-hidden size={14} />
              {prompt}
            </button>
          ))}
        </div>
        <div className="agent-input" aria-label="Graph investigation input">
          <Bot aria-hidden size={15} />
          <span>Ask agent to evaluate evidence relevance...</span>
        </div>
      </section>

      <InvestigationTimeline
        addedEvidence={addedEvidence}
        investigationState={investigationState}
      />
    </aside>
  );
}

function InvestigationPanel({
  addedEvidence,
  investigationState,
  onBackToOverview,
  viewMode,
}: {
  addedEvidence: boolean;
  investigationState: "complete" | "idle" | "running";
  onBackToOverview: () => void;
  viewMode: ViewMode;
}) {
  const toolCalls = [
    "Inspect FDA shortage evidence",
    "Check supplier-level constraints",
    "Search newer API-risk sources",
    "Add supporting evidence",
    "Prepare report context",
  ];
  const isReportReady = viewMode === "report-ready";

  return (
    <aside
      className={cn("risk-side-panel", "investigation-panel", isReportReady && "is-report-ready")}
      aria-label="AI graph investigation"
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
            : "The agent is checking the mapped shortage evidence and looking for one supporting source."}
        </p>
      </section>

      <section className="risk-panel-section">
        <h2>Tool Calls</h2>
        <div className="tool-call-list">
          {toolCalls.map((toolCall, index) => {
            const isDone = isReportReady || index < 3 || (addedEvidence && index < 4);
            const isRunning = investigationState === "running" && !isDone && index === 3;

            return (
              <article
                className={cn("tool-call-item", isDone && "is-done", isRunning && "is-running")}
                key={toolCall}
              >
                <span>
                  {isDone ? (
                    <CheckCircle2 aria-hidden size={14} />
                  ) : isRunning ? (
                    <Loader2 aria-hidden size={14} />
                  ) : (
                    <Bot aria-hidden size={14} />
                  )}
                </span>
                <p>{toolCall}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="risk-panel-section">
        <h2>{isReportReady ? "Report Placeholder" : "Agent Notes"}</h2>
        {isReportReady ? (
          <div className="report-ready-box">
            <strong>Hospital report ready to generate</strong>
            <p>
              The future report can use the action path, mapped evidence, supporting API source, and
              recommended procurement action.
            </p>
          </div>
        ) : (
          <div className="agent-message-list">
            <article>
              <Bot aria-hidden size={15} />
              <p>Action path remains FDA shortage to Accord / Intas GMP constraint.</p>
            </article>
            <article>
              <FileSearch aria-hidden size={15} />
              <p>Searching for one supporting API source without creating a second alert path.</p>
            </article>
          </div>
        )}
      </section>

      <InvestigationTimeline
        addedEvidence={addedEvidence}
        investigationState={investigationState}
      />
    </aside>
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
          text="Risk Path opened for Carboplatin Injection"
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
