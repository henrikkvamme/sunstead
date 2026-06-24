import { createFileRoute } from "@tanstack/react-router";
import { Bell, Command, MapPinned, Search, ShieldAlert } from "lucide-react";

import { FullScreenSupplyRiskGraph, type SupplyGraphEdge, type SupplyGraphNode } from "#/ui/supply-risk";

export const Route = createFileRoute("/dashboard")({
  component: Dashboard,
});

const graphNodes: SupplyGraphNode[] = [
  {
    detail: "Carbapenem antibiotic",
    id: "medicine",
    kind: "medicine",
    label: "Meropenem IV",
    level: "critical",
    metric: "87 risk",
    mobileX: 26,
    mobileY: 32,
    x: 13,
    y: 50,
  },
  {
    detail: "Sterile finished dose",
    id: "component-vial",
    kind: "ingredient",
    label: "Injection vial",
    level: "elevated",
    mobileX: 73,
    mobileY: 42,
    x: 31,
    y: 31,
  },
  {
    detail: "Active ingredient",
    id: "api",
    kind: "ingredient",
    label: "Meropenem API",
    level: "critical",
    metric: "single source",
    mobileX: 26,
    mobileY: 51,
    x: 31,
    y: 66,
  },
  {
    detail: "Approved manufacturer",
    id: "supplier-a",
    kind: "supplier",
    label: "Aster Pharma",
    level: "critical",
    metric: "91% share",
    mobileX: 73,
    mobileY: 63,
    x: 50,
    y: 61,
  },
  {
    detail: "Backup supplier",
    id: "supplier-b",
    kind: "supplier",
    label: "NordChem AB",
    level: "watch",
    metric: "not qualified",
    mobileX: 74,
    mobileY: 26,
    x: 50,
    y: 25,
  },
  {
    detail: "Gujarat API plant",
    id: "facility",
    kind: "facility",
    label: "Vadodara facility",
    level: "critical",
    mobileX: 27,
    mobileY: 70,
    x: 66,
    y: 59,
  },
  {
    detail: "Country concentration",
    id: "country-india",
    kind: "country",
    label: "India",
    level: "critical",
    metric: "91%",
    mobileX: 73,
    mobileY: 79,
    x: 78,
    y: 43,
  },
  {
    detail: "Port route dependency",
    id: "route",
    kind: "country",
    label: "Mundra port",
    level: "elevated",
    mobileX: 27,
    mobileY: 86,
    x: 78,
    y: 75,
  },
  {
    detail: "Severe monsoon alert",
    id: "event",
    kind: "event",
    label: "Flood warning",
    level: "critical",
    metric: "48h",
    mobileX: 74,
    mobileY: 52,
    x: 91,
    y: 27,
  },
  {
    detail: "Reuters, 34 min ago",
    id: "news",
    kind: "news",
    label: "Export delays",
    level: "elevated",
    mobileX: 73,
    mobileY: 93,
    x: 91,
    y: 63,
  },
];

const graphEdges: SupplyGraphEdge[] = [
  { from: "medicine", level: "elevated", to: "component-vial" },
  { from: "medicine", level: "critical", to: "api" },
  { from: "component-vial", level: "watch", to: "supplier-b" },
  { from: "api", level: "critical", to: "supplier-a" },
  { from: "supplier-a", level: "critical", to: "facility" },
  { from: "facility", level: "critical", to: "country-india" },
  { from: "facility", level: "elevated", to: "route" },
  { from: "country-india", level: "critical", to: "event" },
  { from: "route", level: "elevated", to: "news" },
  { from: "event", level: "critical", to: "news" },
];

function Dashboard() {
  return (
    <main className="medicine-graph-screen">
      <nav className="medicine-graph-nav" aria-label="Medicine graph controls">
        <a className="medicine-graph-brand" href="/">
          <span aria-hidden />
          <strong>MedGraph</strong>
        </a>

        <button className="medicine-graph-search" type="button">
          <Search aria-hidden size={15} />
          <span>Meropenem IV</span>
          <kbd>⌘K</kbd>
        </button>

        <div className="medicine-graph-nav-actions">
          <span className="medicine-graph-risk-pill">
            <ShieldAlert aria-hidden size={15} />
            87 critical
          </span>
          <button type="button">
            <MapPinned aria-hidden size={15} />
            Simulate Gujarat flood
          </button>
          <button aria-label="Alerts" className="medicine-graph-alert" type="button">
            <Bell aria-hidden size={16} />
            <span>8</span>
          </button>
          <button aria-label="Open commands" className="medicine-graph-icon" type="button">
            <Command aria-hidden size={16} />
          </button>
        </div>
      </nav>

      <FullScreenSupplyRiskGraph edges={graphEdges} nodes={graphNodes} />
    </main>
  );
}
