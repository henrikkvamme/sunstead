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

type CommandPaletteItem = {
  action: () => void;
  icon: ReactNode;
  id: string;
  meta: string;
  title: string;
  token: string;
};

const selectedMedicineId = "med-meropenem";
const selectedMedicineSlug = "meropenem-iv";
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
    detail: { x: 10, y: 50 },
    id: selectedMedicineId,
    kind: "medicine",
    label: "Meropenem IV",
    metric: "87",
    overview: { x: 50, y: 50 },
    risk: "critical",
    summary: "Carbapenem antibiotic with concentrated upstream API exposure.",
  },
  {
    id: "med-piperacillin",
    kind: "medicine",
    label: "Piperacillin/Tazobactam",
    metric: "64",
    overview: { x: 67, y: 38 },
    risk: "elevated",
    summary: "Shared beta-lactam inputs and tender dependency.",
  },
  {
    id: "med-vancomycin",
    kind: "medicine",
    label: "Vancomycin IV",
    metric: "59",
    overview: { x: 69, y: 60 },
    risk: "elevated",
    summary: "Sterile fill-finish capacity is tightening.",
  },
  {
    id: "med-amoxicillin",
    kind: "medicine",
    label: "Amoxicillin oral",
    metric: "42",
    overview: { x: 50, y: 72 },
    risk: "watch",
    summary: "Seasonal demand pressure, supplier coverage remains adequate.",
  },
  {
    id: "med-propofol",
    kind: "medicine",
    label: "Propofol 10 mg/ml",
    metric: "39",
    overview: { x: 31, y: 60 },
    risk: "watch",
    summary: "Packaging and cold-chain signals require monitoring.",
  },
  {
    id: "med-insulin",
    kind: "medicine",
    label: "Insulin glargine",
    metric: "18",
    overview: { x: 31, y: 38 },
    risk: "stable",
    summary: "Redundant suppliers and stable demand signals.",
  },
  {
    id: "med-saline",
    kind: "medicine",
    label: "Saline bags",
    metric: "21",
    overview: { x: 50, y: 28 },
    risk: "stable",
    summary: "Broad manufacturing base with low active risk.",
  },
  {
    detail: { x: 25, y: 50 },
    id: "component-meropenem-api",
    kind: "component",
    label: "Meropenem API",
    metric: "single source",
    overview: { x: 28, y: 24 },
    risk: "critical",
    summary: "Active ingredient depends on one approved upstream route.",
  },
  {
    id: "component-beta-lactam",
    kind: "component",
    label: "Beta-lactam intermediate",
    metric: "shared",
    overview: { x: 25, y: 77 },
    risk: "elevated",
    summary: "Shared input touches three medicines in the network.",
  },
  {
    id: "component-sterile-vial",
    kind: "component",
    label: "Sterile vial line",
    overview: { x: 27, y: 50 },
    risk: "watch",
    summary: "Fill-finish capacity affects IV presentations.",
  },
  {
    id: "component-cold-chain",
    kind: "component",
    label: "Cold-chain packaging",
    overview: { x: 75, y: 74 },
    risk: "watch",
    summary: "Temperature-controlled packaging dependency for anaesthetic supply.",
  },
  {
    id: "component-glass-vial",
    kind: "component",
    label: "Borosilicate glass",
    overview: { x: 41, y: 18 },
    risk: "stable",
    summary: "Shared sterile container material with broad supplier coverage.",
  },
  {
    id: "component-iv-tubing",
    kind: "component",
    label: "IV tubing resin",
    overview: { x: 37, y: 87 },
    risk: "stable",
    summary: "Commodity input for infusion sets with multiple approved sources.",
  },
  {
    detail: { x: 40, y: 50 },
    id: "supplier-aster",
    kind: "supplier",
    label: "Aster Pharma",
    metric: "91%",
    overview: { x: 16, y: 34 },
    risk: "critical",
    summary: "Approved supplier carries most of the Meropenem API path.",
  },
  {
    id: "supplier-nordchem",
    kind: "supplier",
    label: "NordChem AB",
    metric: "backup",
    overview: { x: 15, y: 66 },
    risk: "watch",
    summary: "Backup supplier exists, but qualification is not complete.",
  },
  {
    id: "supplier-sterifill",
    kind: "supplier",
    label: "SteriFill GmbH",
    overview: { x: 80, y: 64 },
    risk: "stable",
    summary: "Stable sterile fill-finish supplier shared across products.",
  },
  {
    id: "supplier-packline",
    kind: "supplier",
    label: "PackLine Oy",
    overview: { x: 90, y: 68 },
    risk: "stable",
    summary: "Packaging supplier with redundant capacity.",
  },
  {
    id: "supplier-glassworks",
    kind: "supplier",
    label: "GlassWorks Europe",
    overview: { x: 66, y: 18 },
    risk: "stable",
    summary: "Secondary glass vial source for sterile presentations.",
  },
  {
    id: "supplier-medpack",
    kind: "supplier",
    label: "MedPack Baltics",
    overview: { x: 21, y: 92 },
    risk: "stable",
    summary: "Secondary packaging supplier for commodity infusion components.",
  },
  {
    detail: { x: 55, y: 50 },
    id: "place-vadodara",
    kind: "place",
    label: "Vadodara facility",
    metric: "GJ",
    overview: { x: 12, y: 18 },
    risk: "critical",
    summary: "Manufacturing place intersects the active flood warning.",
  },
  {
    id: "place-mundra-port",
    kind: "place",
    label: "Mundra port",
    metric: "route",
    overview: { x: 12, y: 84 },
    risk: "elevated",
    summary: "Export route adds lead-time sensitivity for hospital tenders.",
  },
  {
    id: "place-eu-tender",
    kind: "place",
    label: "EU hospital tenders",
    overview: { x: 82, y: 27 },
    risk: "watch",
    summary: "Tender qualification limits substitution speed.",
  },
  {
    id: "place-frankfurt-hub",
    kind: "place",
    label: "Frankfurt air hub",
    overview: { x: 88, y: 48 },
    risk: "stable",
    summary: "European distribution hub with no active availability risk.",
  },
  {
    id: "place-nordic-buffer",
    kind: "place",
    label: "Nordic buffer stock",
    overview: { x: 58, y: 86 },
    risk: "watch",
    summary: "Regional buffer is adequate but not enough for prolonged API delay.",
  },
  {
    id: "place-copenhagen-depot",
    kind: "place",
    label: "Copenhagen depot",
    overview: { x: 69, y: 78 },
    risk: "stable",
    summary: "Local distribution depot with normal release cadence.",
  },
  {
    detail: { x: 70, y: 50 },
    id: "event-gujarat-flood",
    kind: "event",
    label: "Gujarat flood warning",
    metric: "48h",
    overview: { x: 32, y: 12 },
    risk: "critical",
    summary: "Severe weather signal overlaps the active supplier place.",
  },
  {
    id: "event-seasonal-demand",
    kind: "event",
    label: "Respiratory season",
    overview: { x: 84, y: 82 },
    risk: "watch",
    summary: "Demand pressure is present but not the active driver.",
  },
  {
    id: "event-tender-renewal",
    kind: "event",
    label: "Tender renewal window",
    overview: { x: 91, y: 34 },
    risk: "watch",
    summary: "Contract timing can slow approved supplier substitution.",
  },
  {
    id: "event-theatre-demand",
    kind: "event",
    label: "Surgery schedule lift",
    overview: { x: 72, y: 88 },
    risk: "stable",
    summary: "Planned procedure demand remains inside expected range.",
  },
  {
    detail: { x: 86, y: 38 },
    id: "source-monsoon",
    kind: "source",
    label: "Monsoon bulletin",
    metric: "public",
    overview: { x: 15, y: 8 },
    risk: "critical",
    summary: "Evidence Satellite supporting the flood warning.",
  },
  {
    detail: { x: 86, y: 58 },
    id: "source-export",
    kind: "source",
    label: "Export delay report",
    metric: "source",
    overview: { x: 10, y: 52 },
    risk: "elevated",
    summary: "Evidence Satellite supporting route sensitivity.",
  },
  {
    id: "source-shortage-registry",
    kind: "source",
    label: "Shortage registry",
    overview: { x: 93, y: 16 },
    risk: "stable",
    summary: "No public shortage notice currently visible in the demo data.",
  },
  {
    id: "source-procurement",
    kind: "source",
    label: "Procurement note",
    overview: { x: 74, y: 10 },
    risk: "watch",
    summary: "Internal procurement evidence for tender constraints.",
  },
  {
    id: "source-buffer-report",
    kind: "source",
    label: "Buffer report",
    overview: { x: 46, y: 92 },
    risk: "stable",
    summary: "Internal stock coverage signal for regional buffer.",
  },
  {
    id: "source-release-calendar",
    kind: "source",
    label: "Release calendar",
    overview: { x: 91, y: 88 },
    risk: "stable",
    summary: "Internal release schedule for commodity component replenishment.",
  },
  {
    detail: { x: 86, y: 76 },
    id: scriptedSourceId,
    kind: "source",
    label: "Port operations update",
    metric: "new",
    overview: { x: 18, y: 92 },
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
  { from: "med-propofol", id: "e-propofol-cold-chain", risk: "watch", to: "component-cold-chain" },
  { from: "med-insulin", id: "e-insulin-eu", risk: "stable", to: "place-eu-tender" },
  { from: "med-saline", id: "e-saline-fill", risk: "stable", to: "supplier-sterifill" },
  { from: "med-saline", id: "e-saline-glass", risk: "stable", to: "component-glass-vial" },
  { from: "med-saline", id: "e-saline-tubing", risk: "stable", to: "component-iv-tubing" },
  { from: "component-meropenem-api", id: "e-api-aster", risk: "critical", to: "supplier-aster" },
  { from: "component-beta-lactam", id: "e-shared-aster", risk: "elevated", to: "supplier-aster" },
  {
    from: "component-sterile-vial",
    id: "e-vial-sterifill",
    risk: "watch",
    to: "supplier-sterifill",
  },
  {
    from: "component-sterile-vial",
    id: "e-vial-glassworks",
    risk: "stable",
    to: "supplier-glassworks",
  },
  {
    from: "component-cold-chain",
    id: "e-cold-chain-packline",
    risk: "stable",
    to: "supplier-packline",
  },
  {
    from: "component-iv-tubing",
    id: "e-tubing-medpack",
    risk: "stable",
    to: "supplier-medpack",
  },
  { from: "supplier-aster", id: "e-aster-vadodara", risk: "critical", to: "place-vadodara" },
  { from: "supplier-aster", id: "e-aster-mundra", risk: "elevated", to: "place-mundra-port" },
  { from: "supplier-nordchem", id: "e-nordchem-eu", risk: "watch", to: "place-eu-tender" },
  {
    from: "supplier-sterifill",
    id: "e-sterifill-frankfurt",
    risk: "stable",
    to: "place-frankfurt-hub",
  },
  {
    from: "supplier-packline",
    id: "e-packline-frankfurt",
    risk: "stable",
    to: "place-frankfurt-hub",
  },
  {
    from: "supplier-medpack",
    id: "e-medpack-copenhagen",
    risk: "stable",
    to: "place-copenhagen-depot",
  },
  { from: "place-vadodara", id: "e-vadodara-flood", risk: "critical", to: "event-gujarat-flood" },
  { from: "place-mundra-port", id: "e-mundra-export", risk: "elevated", to: "source-export" },
  { from: "event-gujarat-flood", id: "e-flood-monsoon", risk: "critical", to: "source-monsoon" },
  {
    from: "place-eu-tender",
    id: "e-tender-registry",
    risk: "stable",
    to: "source-shortage-registry",
  },
  { from: "place-eu-tender", id: "e-tender-renewal", risk: "watch", to: "event-tender-renewal" },
  {
    from: "event-tender-renewal",
    id: "e-renewal-procurement",
    risk: "watch",
    to: "source-procurement",
  },
  { from: selectedMedicineId, id: "e-meropenem-buffer", risk: "watch", to: "place-nordic-buffer" },
  {
    from: "place-nordic-buffer",
    id: "e-buffer-report",
    risk: "stable",
    to: "source-buffer-report",
  },
  {
    from: "place-copenhagen-depot",
    id: "e-copenhagen-release",
    risk: "stable",
    to: "source-release-calendar",
  },
  { from: "event-seasonal-demand", id: "e-demand-pip", risk: "watch", to: "med-piperacillin" },
  { from: "event-theatre-demand", id: "e-demand-propofol", risk: "stable", to: "med-propofol" },
  {
    from: "event-gujarat-flood",
    id: "e-flood-newer-port",
    risk: "elevated",
    scripted: true,
    to: scriptedSourceId,
  },
];

const medicineSupplyChainEdges: Record<string, string[]> = {
  [selectedMedicineId]: [
    "e-meropenem-api",
    "e-api-aster",
    "e-aster-vadodara",
    "e-vadodara-flood",
    "e-flood-monsoon",
    "e-aster-mundra",
    "e-mundra-export",
    "e-meropenem-vial",
    "e-vial-sterifill",
    "e-vial-glassworks",
    "e-sterifill-frankfurt",
    "e-meropenem-buffer",
    "e-buffer-report",
  ],
  "med-piperacillin": [
    "e-pip-shared",
    "e-shared-aster",
    "e-aster-vadodara",
    "e-vadodara-flood",
    "e-flood-monsoon",
    "e-aster-mundra",
    "e-mundra-export",
    "e-demand-pip",
  ],
  "med-vancomycin": [
    "e-vanco-vial",
    "e-vial-sterifill",
    "e-vial-glassworks",
    "e-sterifill-frankfurt",
  ],
  "med-amoxicillin": [
    "e-amox-shared",
    "e-shared-aster",
    "e-aster-vadodara",
    "e-vadodara-flood",
    "e-flood-monsoon",
    "e-aster-mundra",
    "e-mundra-export",
  ],
  "med-propofol": [
    "e-propofol-fill",
    "e-sterifill-frankfurt",
    "e-propofol-cold-chain",
    "e-cold-chain-packline",
    "e-packline-frankfurt",
    "e-demand-propofol",
  ],
  "med-insulin": [
    "e-insulin-eu",
    "e-nordchem-eu",
    "e-tender-registry",
    "e-tender-renewal",
    "e-renewal-procurement",
  ],
  "med-saline": [
    "e-saline-fill",
    "e-saline-glass",
    "e-saline-tubing",
    "e-vial-sterifill",
    "e-vial-glassworks",
    "e-sterifill-frankfurt",
    "e-tubing-medpack",
    "e-medpack-copenhagen",
    "e-copenhagen-release",
  ],
};

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
  medicine: <Pill aria-hidden size={16} />,
  place: <MapPin aria-hidden size={15} />,
  source: <FileText aria-hidden size={14} />,
  supplier: <Factory aria-hidden size={15} />,
};

function SanitasLogoMark() {
  return (
    <svg
      aria-hidden
      className="sanitas-logo-mark"
      fill="none"
      viewBox="0 0 32 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        className="sanitas-logo-orbit"
        d="M5.7 13.8C8.7 5.6 22.9 3.7 27.2 9.3c3.9 5.1-4.8 11.8-15 9.8C5.3 17.7 2 13.6 5.4 9.8"
      />
      <rect
        className="sanitas-logo-medicine sanitas-logo-medicine-left"
        height="9.2"
        rx="2.4"
        width="8.2"
        x="8.3"
        y="7.3"
      />
      <rect
        className="sanitas-logo-medicine sanitas-logo-medicine-right"
        height="9.2"
        rx="4.1"
        width="8.2"
        x="16.1"
        y="7.3"
      />
      <path className="sanitas-logo-medicine-detail" d="M12.4 8.9v6" />
      <circle className="sanitas-logo-risk-dot" cx="25.8" cy="8.2" r="2.1" />
    </svg>
  );
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

function buildGraphDepths(nodes: GraphNode[], edges: GraphEdge[]) {
  const visibleIds = new Set(nodes.map((node) => node.id));
  const adjacency = new Map<string, string[]>();

  for (const node of nodes) {
    adjacency.set(node.id, []);
  }

  for (const edge of edges) {
    if (!visibleIds.has(edge.from) || !visibleIds.has(edge.to)) {
      continue;
    }

    adjacency.get(edge.from)?.push(edge.to);
    adjacency.get(edge.to)?.push(edge.from);
  }

  const depths = new Map<string, number>([[selectedMedicineId, 0]]);
  const queue = [selectedMedicineId];

  for (let index = 0; index < queue.length; index += 1) {
    const current = queue[index];
    const nextDepth = (depths.get(current) ?? 0) + 1;

    for (const next of adjacency.get(current) ?? []) {
      if (depths.has(next)) {
        continue;
      }

      depths.set(next, nextDepth);
      queue.push(next);
    }
  }

  return depths;
}

export function Dashboard() {
  const [mode, setMode] = useState<GraphMode>("overview");
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

  const activePath = useMemo(
    () => new Set(addedEvidence ? [...riskPathBase, scriptedSourceId] : riskPathBase),
    [addedEvidence],
  );
  const selectedNode = graphNodes.find((node) => node.id === selectedNodeId) ?? graphNodes[0];
  const selectedDetails = nodeDetails[selectedNode.id] ?? nodeDetails[selectedMedicineId];
  const evidenceCount = addedEvidence ? 5 : 4;
  const confidence = addedEvidence ? "92%" : "88%";

  const openCommandPalette = () => {
    setCommandPaletteOpen(true);
  };

  const showOverview = () => {
    setMode("overview");
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

      setMode(nextMode);
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
    setMode("focused");
    setSelectedNodeId(selectedMedicineId);
    writeUrlGraphMode("focused");
  };

  const startInvestigation = () => {
    if (investigationState === "running") {
      return;
    }

    setMode("focused");
    setSelectedNodeId("event-gujarat-flood");
    setInvestigationState("running");
    writeUrlGraphMode("focused");
  };

  const selectCommandNode = (node: GraphNode) => {
    if (node.id === selectedMedicineId) {
      focusMedicine();
      return;
    }

    setSelectedNodeId(node.id);
    setMode("focused");
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
    <main className={cn("medicine-graph-screen", `is-${mode}`)}>
      <nav className="medicine-graph-nav" aria-label="Medicine graph controls">
        <button className="medicine-graph-brand" type="button" onClick={showOverview}>
          <SanitasLogoMark />
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
            {mode === "overview" ? "Find medicine, supplier, source" : selectedNode.label}
          </span>
          <kbd>⌘K</kbd>
        </button>

        <div className="medicine-graph-nav-actions">
          <span className={cn("medicine-graph-risk-pill", mode === "focused" && "is-critical")}>
            <ShieldAlert aria-hidden size={15} />
            {mode === "overview" ? "7 medicines" : "87 critical"}
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
        <div className="graph-status-strip" aria-hidden>
          <span>Medicine Risk Network</span>
          <span>{mode === "overview" ? "Network Overview" : "Medicine Risk Graph"}</span>
          <span>{mode === "overview" ? "Hospital medicines" : "Supplier chain mapped"}</span>
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
              writeUrlGraphMode("focused");
            }
          }}
        />
      </section>

      {mode === "focused" ? (
        <RiskSidePanel
          key={selectedNode.id}
          addedEvidence={addedEvidence}
          confidence={confidence}
          details={selectedDetails}
          evidenceCount={evidenceCount}
          investigationState={investigationState}
          mode={mode}
          node={selectedNode}
          onBackToOverview={showOverview}
          onStartInvestigation={startInvestigation}
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
  const visibleNodes = graphNodes
    .filter((node) => node.id !== scriptedSourceId || addedEvidence)
    .filter((node) => mode === "overview" || activePath.has(node.id) || node.id === selectedNodeId);
  const byId = new Map(visibleNodes.map((node) => [node.id, node]));
  const visibleEdges = graphEdges.filter(
    (edge) => (!edge.scripted || addedEvidence) && byId.has(edge.from) && byId.has(edge.to),
  );
  const hoveredNode = hoveredNodeId ? byId.get(hoveredNodeId) : null;
  const overviewLayout = buildOverviewLayout(visibleNodes);
  const graphDepths = buildGraphDepths(visibleNodes, visibleEdges);

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
        {visibleEdges.map((edge, index) => {
          const isActive = activePath.has(edge.from) && activePath.has(edge.to);
          const edgeDepth = Math.min(
            graphDepths.get(edge.from) ?? visibleNodes.length,
            graphDepths.get(edge.to) ?? visibleNodes.length,
          );
          const edgeStyle = {
            "--link-delay": `${Math.min(edgeDepth * 90 + index * 9, 640)}ms`,
          } as CSSProperties;

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
              style={edgeStyle}
            />
          );
        })}
      </svg>

      {visibleNodes.map((node, index) => {
        const point = pointFor(node);
        const isActive = activePath.has(node.id);
        const isDimmed = mode === "focused" && !isActive && node.id !== selectedMedicineId;
        const isSource = node.kind === "source";
        const nodeDepth = graphDepths.get(node.id) ?? 5;
        const nodeStyle = {
          "--node-delay": `${Math.min(nodeDepth * 92 + index * 8, 680)}ms`,
          left: `${point.x}%`,
          top: `${point.y}%`,
        } as CSSProperties;

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
