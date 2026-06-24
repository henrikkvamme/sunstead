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
  Hospital,
  Loader2,
  MapPin,
  Route as RouteIcon,
  Search,
  ShieldAlert,
  Sparkles,
  Waves,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { cn } from "#/lib/cn";

export const Route = createFileRoute("/dashboard")({
  component: Dashboard,
});

type GraphMode = "focused" | "overview";
type RiskLevel = "critical" | "elevated" | "stable" | "watch";

type GraphNode = {
  detail?: { x: number; y: number };
  id: string;
  kind: "component" | "event" | "medicine" | "place" | "source" | "supplier";
  label: string;
  metric?: string;
  overview: { x: number; y: number };
  risk: RiskLevel;
  summary: string;
};

type GraphEdge = {
  from: string;
  id: string;
  risk: RiskLevel;
  scripted?: true;
  to: string;
};

type NodeDetails = Record<
  string,
  {
    confidence: string;
    facts: string[];
    prompts: string[];
    sources: { meta: string; title: string; url: string }[];
    whyItMatters: string;
  }
>;

const selectedMedicineId = "med-meropenem";
const scriptedSourceId = "source-newer-port";

const riskPathBase = [
  "med-meropenem",
  "component-meropenem-api",
  "supplier-aster",
  "place-vadodara",
  "event-gujarat-flood",
  "source-monsoon",
  "source-export",
];

const graphNodes: GraphNode[] = [
  {
    detail: { x: 17, y: 50 },
    id: selectedMedicineId,
    kind: "medicine",
    label: "Meropenem IV",
    metric: "87",
    overview: { x: 47, y: 47 },
    risk: "critical",
    summary: "Carbapenem antibiotic with concentrated upstream API exposure.",
  },
  {
    id: "med-piperacillin",
    kind: "medicine",
    label: "Piperacillin/Tazobactam",
    metric: "64",
    overview: { x: 53, y: 40 },
    risk: "elevated",
    summary: "Shared beta-lactam inputs and tender dependency.",
  },
  {
    id: "med-vancomycin",
    kind: "medicine",
    label: "Vancomycin IV",
    metric: "59",
    overview: { x: 58, y: 51 },
    risk: "elevated",
    summary: "Sterile fill-finish capacity is tightening.",
  },
  {
    id: "med-amoxicillin",
    kind: "medicine",
    label: "Amoxicillin oral",
    metric: "42",
    overview: { x: 43, y: 57 },
    risk: "watch",
    summary: "Seasonal demand pressure, supplier coverage remains adequate.",
  },
  {
    id: "med-propofol",
    kind: "medicine",
    label: "Propofol 10 mg/ml",
    metric: "39",
    overview: { x: 39, y: 44 },
    risk: "watch",
    summary: "Packaging and cold-chain signals require monitoring.",
  },
  {
    id: "med-insulin",
    kind: "medicine",
    label: "Insulin glargine",
    metric: "18",
    overview: { x: 51, y: 61 },
    risk: "stable",
    summary: "Redundant suppliers and stable demand signals.",
  },
  {
    id: "med-saline",
    kind: "medicine",
    label: "Saline bags",
    metric: "21",
    overview: { x: 61, y: 43 },
    risk: "stable",
    summary: "Broad manufacturing base with low active risk.",
  },
  {
    detail: { x: 31, y: 50 },
    id: "component-meropenem-api",
    kind: "component",
    label: "Meropenem API",
    metric: "single source",
    overview: { x: 31, y: 33 },
    risk: "critical",
    summary: "Active ingredient depends on one approved upstream route.",
  },
  {
    id: "component-beta-lactam",
    kind: "component",
    label: "Beta-lactam intermediate",
    metric: "shared",
    overview: { x: 30, y: 58 },
    risk: "elevated",
    summary: "Shared input touches three medicines in the network.",
  },
  {
    id: "component-sterile-vial",
    kind: "component",
    label: "Sterile vial line",
    overview: { x: 31, y: 46 },
    risk: "watch",
    summary: "Fill-finish capacity affects IV presentations.",
  },
  {
    detail: { x: 45, y: 50 },
    id: "supplier-aster",
    kind: "supplier",
    label: "Aster Pharma",
    metric: "91%",
    overview: { x: 20, y: 38 },
    risk: "critical",
    summary: "Approved supplier carries most of the Meropenem API path.",
  },
  {
    id: "supplier-nordchem",
    kind: "supplier",
    label: "NordChem AB",
    metric: "backup",
    overview: { x: 20, y: 62 },
    risk: "watch",
    summary: "Backup supplier exists, but qualification is not complete.",
  },
  {
    id: "supplier-sterifill",
    kind: "supplier",
    label: "SteriFill GmbH",
    overview: { x: 72, y: 57 },
    risk: "stable",
    summary: "Stable sterile fill-finish supplier shared across products.",
  },
  {
    detail: { x: 59, y: 50 },
    id: "place-vadodara",
    kind: "place",
    label: "Vadodara facility",
    metric: "GJ",
    overview: { x: 12, y: 45 },
    risk: "critical",
    summary: "Manufacturing place intersects the active flood warning.",
  },
  {
    id: "place-mundra-port",
    kind: "place",
    label: "Mundra port",
    metric: "route",
    overview: { x: 12, y: 72 },
    risk: "elevated",
    summary: "Export route adds lead-time sensitivity for hospital tenders.",
  },
  {
    id: "place-eu-tender",
    kind: "place",
    label: "EU hospital tenders",
    overview: { x: 79, y: 36 },
    risk: "watch",
    summary: "Tender qualification limits substitution speed.",
  },
  {
    detail: { x: 73, y: 50 },
    id: "event-gujarat-flood",
    kind: "event",
    label: "Gujarat flood warning",
    metric: "48h",
    overview: { x: 8, y: 25 },
    risk: "critical",
    summary: "Severe weather signal overlaps the active supplier place.",
  },
  {
    id: "event-seasonal-demand",
    kind: "event",
    label: "Respiratory season",
    overview: { x: 82, y: 67 },
    risk: "watch",
    summary: "Demand pressure is present but not the active driver.",
  },
  {
    detail: { x: 86, y: 39 },
    id: "source-monsoon",
    kind: "source",
    label: "Monsoon bulletin",
    metric: "public",
    overview: { x: 4, y: 13 },
    risk: "critical",
    summary: "Evidence Satellite supporting the flood warning.",
  },
  {
    detail: { x: 86, y: 58 },
    id: "source-export",
    kind: "source",
    label: "Export delay report",
    metric: "source",
    overview: { x: 4, y: 39 },
    risk: "elevated",
    summary: "Evidence Satellite supporting route sensitivity.",
  },
  {
    id: "source-shortage-registry",
    kind: "source",
    label: "Shortage registry",
    overview: { x: 91, y: 24 },
    risk: "stable",
    summary: "No public shortage notice currently visible in the demo data.",
  },
  {
    detail: { x: 86, y: 72 },
    id: scriptedSourceId,
    kind: "source",
    label: "Port operations update",
    metric: "new",
    overview: { x: 6, y: 55 },
    risk: "elevated",
    summary: "Scripted new evidence added by the Graph Intelligence Agent.",
  },
];

const graphEdges: GraphEdge[] = [
  {
    from: selectedMedicineId,
    id: "e-meropenem-api",
    risk: "critical",
    to: "component-meropenem-api",
  },
  { from: selectedMedicineId, id: "e-meropenem-vial", risk: "watch", to: "component-sterile-vial" },
  { from: "med-piperacillin", id: "e-pip-shared", risk: "elevated", to: "component-beta-lactam" },
  { from: "med-amoxicillin", id: "e-amox-shared", risk: "watch", to: "component-beta-lactam" },
  { from: "med-vancomycin", id: "e-vanco-vial", risk: "elevated", to: "component-sterile-vial" },
  { from: "med-propofol", id: "e-propofol-fill", risk: "watch", to: "supplier-sterifill" },
  { from: "med-insulin", id: "e-insulin-eu", risk: "stable", to: "place-eu-tender" },
  { from: "med-saline", id: "e-saline-fill", risk: "stable", to: "supplier-sterifill" },
  { from: "component-meropenem-api", id: "e-api-aster", risk: "critical", to: "supplier-aster" },
  { from: "component-beta-lactam", id: "e-shared-aster", risk: "elevated", to: "supplier-aster" },
  {
    from: "component-sterile-vial",
    id: "e-vial-sterifill",
    risk: "watch",
    to: "supplier-sterifill",
  },
  { from: "supplier-aster", id: "e-aster-vadodara", risk: "critical", to: "place-vadodara" },
  { from: "supplier-aster", id: "e-aster-mundra", risk: "elevated", to: "place-mundra-port" },
  { from: "supplier-nordchem", id: "e-nordchem-eu", risk: "watch", to: "place-eu-tender" },
  { from: "place-vadodara", id: "e-vadodara-flood", risk: "critical", to: "event-gujarat-flood" },
  { from: "place-mundra-port", id: "e-mundra-export", risk: "elevated", to: "source-export" },
  { from: "event-gujarat-flood", id: "e-flood-monsoon", risk: "critical", to: "source-monsoon" },
  {
    from: "place-eu-tender",
    id: "e-tender-registry",
    risk: "stable",
    to: "source-shortage-registry",
  },
  { from: "event-seasonal-demand", id: "e-demand-pip", risk: "watch", to: "med-piperacillin" },
  {
    from: "event-gujarat-flood",
    id: "e-flood-newer-port",
    risk: "elevated",
    scripted: true,
    to: scriptedSourceId,
  },
];

const nodeDetails: NodeDetails = {
  [selectedMedicineId]: {
    confidence: "High confidence, 4 Evidence Sources",
    facts: [
      "Supply fragility: high",
      "Demand pressure: stable",
      "Evidence strength: high",
      "Action window: 48 hours",
    ],
    prompts: [
      "Find newer evidence",
      "Explain risk path",
      "Check demand pressure",
      "Review alternate supplier readiness",
    ],
    sources: [
      {
        meta: "Demo source",
        title: "Monsoon bulletin for Gujarat",
        url: "https://mausam.imd.gov.in/",
      },
      {
        meta: "Demo source",
        title: "Export delay monitoring",
        url: "https://www.reuters.com/world/india/",
      },
    ],
    whyItMatters:
      "Meropenem IV is used in time-sensitive hospital treatment where delayed availability can affect patient care.",
  },
  "component-meropenem-api": {
    confidence: "Critical contribution",
    facts: [
      "Single approved API route",
      "Backup supplier not qualified",
      "No patient data represented",
    ],
    prompts: ["Find newer evidence", "Review alternate supplier readiness"],
    sources: [
      {
        meta: "Internal graph",
        title: "Approved supplier mapping",
        url: "https://example.com/sanitas-demo",
      },
    ],
    whyItMatters:
      "The API is the upstream component that carries the active Supply Risk into Medicine Availability.",
  },
  "supplier-aster": {
    confidence: "91% supplier share",
    facts: [
      "Primary approved manufacturer",
      "Dependent on Vadodara facility",
      "Backup supplier requires qualification",
    ],
    prompts: ["Find newer evidence", "Review alternate supplier readiness"],
    sources: [
      {
        meta: "Demo source",
        title: "Supplier qualification register",
        url: "https://example.com/sanitas-demo",
      },
    ],
    whyItMatters:
      "Aster Pharma is the supplier link between the API and the affected manufacturing place.",
  },
  "place-vadodara": {
    confidence: "High place relevance",
    facts: [
      "Active facility place",
      "Weather signal overlaps facility region",
      "Route sensitivity through Mundra port",
    ],
    prompts: ["Find newer evidence", "Explain risk path"],
    sources: [
      {
        meta: "Demo source",
        title: "Regional weather bulletin",
        url: "https://mausam.imd.gov.in/",
      },
    ],
    whyItMatters:
      "This place is where the supplier exposure becomes operational for the focused medicine.",
  },
  "event-gujarat-flood": {
    confidence: "3 supporting sources",
    facts: [
      "48 hour severe weather signal",
      "Linked to supplier place",
      "Availability risk level reflects medicine exposure",
    ],
    prompts: ["Find newer evidence", "Explain risk path"],
    sources: [
      {
        meta: "Public weather",
        title: "Monsoon bulletin for Gujarat",
        url: "https://mausam.imd.gov.in/",
      },
      {
        meta: "Logistics watch",
        title: "Port operations monitoring",
        url: "https://www.reuters.com/world/india/",
      },
    ],
    whyItMatters:
      "The flood warning matters because it intersects the mapped supplier path for Meropenem IV.",
  },
  "source-monsoon": {
    confidence: "Primary Evidence Satellite",
    facts: [
      "Supports the flood warning",
      "Public source placeholder",
      "Opened deliberately from the panel",
    ],
    prompts: ["Find newer evidence"],
    sources: [
      {
        meta: "Public weather",
        title: "Monsoon bulletin for Gujarat",
        url: "https://mausam.imd.gov.in/",
      },
    ],
    whyItMatters:
      "This Evidence Satellite supports the active event that drives the focused Risk Path.",
  },
  "source-export": {
    confidence: "Secondary Evidence Satellite",
    facts: ["Supports export route sensitivity", "Does not add a supplier-chain branch"],
    prompts: ["Find newer evidence"],
    sources: [
      {
        meta: "News monitor",
        title: "Export delay monitoring",
        url: "https://www.reuters.com/world/india/",
      },
    ],
    whyItMatters:
      "This source explains why lead time can change even when the supplier chain is already mapped.",
  },
  [scriptedSourceId]: {
    confidence: "New evidence added",
    facts: [
      "Added by scripted Graph Investigation",
      "Evidence only",
      "Risk confidence increased modestly",
    ],
    prompts: ["Explain risk path", "Review alternate supplier readiness"],
    sources: [
      {
        meta: "New source",
        title: "Port operations update",
        url: "https://www.reuters.com/world/india/",
      },
    ],
    whyItMatters:
      "The new evidence strengthens the route-risk explanation without changing the supplier chain.",
  },
};

const kindIcons: Record<GraphNode["kind"], ReactNode> = {
  component: <FlaskConical aria-hidden size={15} />,
  event: <Waves aria-hidden size={15} />,
  medicine: <Hospital aria-hidden size={16} />,
  place: <MapPin aria-hidden size={15} />,
  source: <FileText aria-hidden size={14} />,
  supplier: <Factory aria-hidden size={15} />,
};

export function Dashboard() {
  const [mode, setMode] = useState<GraphMode>("overview");
  const [selectedNodeId, setSelectedNodeId] = useState(selectedMedicineId);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [investigationState, setInvestigationState] = useState<"idle" | "running" | "complete">(
    "idle",
  );
  const [addedEvidence, setAddedEvidence] = useState(false);
  const [pulsePath, setPulsePath] = useState(false);

  const activePath = useMemo(
    () => new Set(addedEvidence ? [...riskPathBase, scriptedSourceId] : riskPathBase),
    [addedEvidence],
  );
  const selectedNode = graphNodes.find((node) => node.id === selectedNodeId) ?? graphNodes[0];
  const selectedDetails = nodeDetails[selectedNode.id] ?? nodeDetails[selectedMedicineId];
  const evidenceCount = addedEvidence ? 5 : 4;
  const confidence = addedEvidence ? "92%" : "88%";

  useEffect(() => {
    if (investigationState !== "running") {
      return;
    }

    const finish = window.setTimeout(() => {
      setAddedEvidence(true);
      setInvestigationState("complete");
      setPulsePath(true);
    }, 2100);
    const clearPulse = window.setTimeout(() => setPulsePath(false), 3400);

    return () => {
      window.clearTimeout(finish);
      window.clearTimeout(clearPulse);
    };
  }, [investigationState]);

  const focusMedicine = () => {
    setMode("focused");
    setSelectedNodeId(selectedMedicineId);
  };

  const startInvestigation = () => {
    if (investigationState === "running") {
      return;
    }

    setMode("focused");
    setSelectedNodeId("event-gujarat-flood");
    setInvestigationState("running");
  };

  return (
    <main className={cn("medicine-graph-screen", `is-${mode}`)}>
      <nav className="medicine-graph-nav" aria-label="Medicine graph controls">
        <button className="medicine-graph-brand" type="button" onClick={() => setMode("overview")}>
          <span aria-hidden />
          <strong>Sanitas</strong>
        </button>

        <button className="medicine-graph-search" type="button">
          <Search aria-hidden size={15} />
          <span>
            {mode === "overview" ? "Search medicines, suppliers, sources..." : "Meropenem IV"}
          </span>
          <kbd>⌘K</kbd>
        </button>

        <div className="medicine-graph-nav-actions">
          <span className={cn("medicine-graph-risk-pill", mode === "focused" && "is-critical")}>
            <ShieldAlert aria-hidden size={15} />
            {mode === "overview" ? "1 critical path" : "87 critical"}
          </span>
          <button type="button" onClick={startInvestigation}>
            <FileSearch aria-hidden size={15} />
            Investigate latest evidence
          </button>
          <button aria-label="Graph Change Timeline" className="medicine-graph-alert" type="button">
            <Bell aria-hidden size={16} />
            <span>{addedEvidence ? 5 : 4}</span>
          </button>
          <button aria-label="Open commands" className="medicine-graph-icon" type="button">
            <Command aria-hidden size={16} />
          </button>
        </div>
      </nav>

      <section className="medicine-graph-stage" aria-label="Medicine Risk Network">
        <div className="graph-status-strip" aria-hidden>
          <span>Medicine Risk Network</span>
          <span>{mode === "overview" ? "Network Overview" : "Medicine Risk Graph"}</span>
          <span>Supplier chain pre-mapped</span>
        </div>

        <MedicineRiskGraph
          activePath={activePath}
          addedEvidence={addedEvidence}
          hoveredNodeId={hoveredNodeId}
          mode={mode}
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
            if (mode === "overview") {
              setMode("focused");
            }
          }}
        />
      </section>

      <RiskSidePanel
        key={selectedNode.id}
        addedEvidence={addedEvidence}
        confidence={confidence}
        details={selectedDetails}
        evidenceCount={evidenceCount}
        investigationState={investigationState}
        mode={mode}
        node={selectedNode}
        onBackToOverview={() => setMode("overview")}
        onStartInvestigation={startInvestigation}
      />
    </main>
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
  const visibleNodes = graphNodes.filter((node) => node.id !== scriptedSourceId || addedEvidence);
  const byId = new Map(visibleNodes.map((node) => [node.id, node]));
  const visibleEdges = graphEdges.filter(
    (edge) => (!edge.scripted || addedEvidence) && byId.has(edge.from) && byId.has(edge.to),
  );
  const hoveredNode = hoveredNodeId ? byId.get(hoveredNodeId) : null;

  const pointFor = (node: GraphNode) =>
    mode === "focused" && node.detail ? node.detail : node.overview;
  const pathFor = (edge: GraphEdge) => {
    const from = byId.get(edge.from);
    const to = byId.get(edge.to);

    if (!from || !to) {
      return "";
    }

    const fromPoint = pointFor(from);
    const toPoint = pointFor(to);
    const controlOffset = mode === "focused" ? 6 : 11;
    const midX = (fromPoint.x + toPoint.x) / 2;

    return `M ${fromPoint.x} ${fromPoint.y} C ${midX} ${fromPoint.y - controlOffset}, ${midX} ${
      toPoint.y + controlOffset
    }, ${toPoint.x} ${toPoint.y}`;
  };

  return (
    <div className={cn("medicine-risk-graph", `is-${mode}`, pulsePath && "is-pulsing")}>
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
        {visibleEdges.map((edge) => {
          const isActive = activePath.has(edge.from) && activePath.has(edge.to);

          return (
            <path
              className={cn(
                "medicine-risk-link",
                `risk-${edge.risk}`,
                isActive && "is-active",
                edge.scripted && "is-scripted",
              )}
              d={pathFor(edge)}
              key={edge.id}
              pathLength="1"
            />
          );
        })}
      </svg>

      {visibleNodes.map((node) => {
        const point = pointFor(node);
        const isActive = activePath.has(node.id);
        const isDimmed = mode === "focused" && !isActive && node.id !== selectedMedicineId;
        const isSource = node.kind === "source";

        return (
          <button
            aria-label={`${node.label}: ${node.summary}`}
            className={cn(
              "medicine-risk-node",
              `node-${node.kind}`,
              `risk-${node.risk}`,
              isActive && "is-active-path",
              isDimmed && "is-dimmed",
              selectedNodeId === node.id && "is-selected",
              node.id === selectedMedicineId && "is-critical-medicine",
              node.id === scriptedSourceId && "is-new-evidence",
              isSource && "is-evidence-satellite",
            )}
            key={node.id}
            onClick={() => {
              if (node.id === selectedMedicineId) {
                onFocusMedicine();
                return;
              }

              onSelectNode(node);
            }}
            onMouseEnter={() => onHoverNode(node.id)}
            onMouseLeave={() => onHoverNode(null)}
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
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
  return (
    <div
      className={cn("graph-hover-preview", `risk-${node.risk}`, mode === "focused" && "is-focused")}
      style={{ left: `${Math.min(point.x + 2, 76)}%`, top: `${Math.max(point.y - 9, 12)}%` }}
    >
      <span>{node.kind}</span>
      <strong>{node.label}</strong>
      <p>{node.summary}</p>
    </div>
  );
}

function RiskSidePanel({
  addedEvidence,
  confidence,
  details,
  evidenceCount,
  investigationState,
  mode,
  node,
  onBackToOverview,
  onStartInvestigation,
}: {
  addedEvidence: boolean;
  confidence: string;
  details: NodeDetails[string];
  evidenceCount: number;
  investigationState: "complete" | "idle" | "running";
  mode: GraphMode;
  node: GraphNode;
  onBackToOverview: () => void;
  onStartInvestigation: () => void;
}) {
  const isSource = node.kind === "source";
  const primarySource = details.sources[0];

  return (
    <aside className="risk-side-panel" aria-label="Risk Profile and node investigation">
      <div className="risk-panel-head">
        <button type="button" onClick={onBackToOverview}>
          <ChevronLeft aria-hidden size={15} />
          Network
        </button>
        <span>{mode === "overview" ? "Overview" : "Focused graph"}</span>
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
            <strong>{node.id === selectedMedicineId ? "87" : node.risk}</strong>
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
          Used in time-sensitive hospital treatment where delayed availability can affect patient
          care.
        </p>
      </section>

      <section className="risk-panel-section">
        <h2>Recommended Action</h2>
        <div className="recommendation-box">
          <strong>Prepare alternate supplier order</strong>
          <p>
            Verify approved supplier availability and lead time before stock falls below safety
            threshold.
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

function InvestigationTimeline({
  addedEvidence,
  investigationState,
}: {
  addedEvidence: boolean;
  investigationState: "complete" | "idle" | "running";
}) {
  const runningSteps = [
    "Searching newer public sources",
    "Evaluating relevance to Vadodara path",
    "Preparing graph evidence update",
  ];

  return (
    <section className="risk-panel-section timeline-section">
      <h2>Graph Change Timeline</h2>
      <div className="timeline-list">
        <TimelineItem
          icon={<Activity aria-hidden size={14} />}
          text="Risk Path opened for Meropenem IV"
        />
        <TimelineItem
          icon={<RouteIcon aria-hidden size={14} />}
          text="Supplier chain kept unchanged"
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
            text="Added Port operations update Evidence Satellite"
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
