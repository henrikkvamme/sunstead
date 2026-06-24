import { AlertTriangle, ArrowUpRight, Factory, FileText, Globe2, Hospital, Pill, RadioTower, Route, Waves } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { cn } from "#/lib/cn";

export type RiskLevel = "critical" | "elevated" | "stable" | "watch";

export type SupplyGraphNode = {
  detail: string;
  id: string;
  kind: "country" | "event" | "facility" | "ingredient" | "medicine" | "news" | "supplier";
  label: string;
  level: RiskLevel;
  metric?: string;
  mobileX?: number;
  mobileY?: number;
  x: number;
  y: number;
};

export type SupplyGraphEdge = {
  from: string;
  level: RiskLevel;
  to: string;
};

const kindIcons: Record<SupplyGraphNode["kind"], ReactNode> = {
  country: <Globe2 aria-hidden size={16} />,
  event: <Waves aria-hidden size={16} />,
  facility: <Factory aria-hidden size={16} />,
  ingredient: <Pill aria-hidden size={16} />,
  medicine: <Hospital aria-hidden size={17} />,
  news: <FileText aria-hidden size={16} />,
  supplier: <Route aria-hidden size={16} />,
};

export function SupplyRiskSummary({
  children,
  level,
  metric,
  title,
}: {
  children: ReactNode;
  level: RiskLevel;
  metric: string;
  title: string;
}) {
  return (
    <article className={cn("risk-summary-card", `risk-${level}`)}>
      <div>
        <span>{title}</span>
        <strong>{metric}</strong>
      </div>
      <p>{children}</p>
    </article>
  );
}

export function SupplyRiskGraph({
  edges,
  nodes,
}: {
  edges: SupplyGraphEdge[];
  nodes: SupplyGraphNode[];
}) {
  const byId = new Map(nodes.map((node) => [node.id, node]));

  return (
    <section className="supply-graph-panel" aria-label="Medicine supply chain risk graph">
      <div className="supply-graph-toolbar">
        <div>
          <p>Neo4j graph view</p>
          <h2>Meropenem IV supply risk propagation</h2>
        </div>
        <div className="risk-filter-strip" aria-label="Risk filters">
          <span className="risk-critical">Critical</span>
          <span className="risk-elevated">Elevated</span>
          <span className="risk-watch">Watch</span>
          <span className="risk-stable">Stable</span>
        </div>
      </div>

      <div className="supply-graph-canvas">
        <svg aria-hidden className="supply-graph-links" viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs>
            <linearGradient id="risk-hot-link" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#ff5a0a" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#ff2d20" stopOpacity="0.78" />
            </linearGradient>
            <linearGradient id="risk-cool-link" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#767676" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#a0a0a0" stopOpacity="0.45" />
            </linearGradient>
          </defs>
          {edges.map((edge) => {
            const from = byId.get(edge.from);
            const to = byId.get(edge.to);

            if (!from || !to) {
              return null;
            }

            const midX = (from.x + to.x) / 2;
            const curve = `M ${from.x} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${to.x} ${to.y}`;

            return (
              <path
                className={cn("supply-graph-link", `risk-${edge.level}`)}
                d={curve}
                key={`${edge.from}-${edge.to}`}
                pathLength="1"
              />
            );
          })}
        </svg>

        {nodes.map((node) => (
          <button
            className={cn("supply-graph-node", `risk-${node.level}`, `node-${node.kind}`)}
            key={node.id}
            style={{ left: `${node.x}%`, top: `${node.y}%` }}
            type="button"
          >
            <span>{kindIcons[node.kind]}</span>
            <strong>{node.label}</strong>
            <small>{node.detail}</small>
            {node.metric ? <em>{node.metric}</em> : null}
          </button>
        ))}
      </div>
    </section>
  );
}

export function FullScreenSupplyRiskGraph({
  edges,
  nodes,
}: {
  edges: SupplyGraphEdge[];
  nodes: SupplyGraphNode[];
}) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const curveFor = (edge: SupplyGraphEdge, coordinateSet: "desktop" | "mobile") => {
    const from = byId.get(edge.from);
    const to = byId.get(edge.to);

    if (!from || !to) {
      return null;
    }

    const fromX = coordinateSet === "mobile" ? (from.mobileX ?? from.x) : from.x;
    const fromY = coordinateSet === "mobile" ? (from.mobileY ?? from.y) : from.y;
    const toX = coordinateSet === "mobile" ? (to.mobileX ?? to.x) : to.x;
    const toY = coordinateSet === "mobile" ? (to.mobileY ?? to.y) : to.y;
    const midX = (fromX + toX) / 2;

    return `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`;
  };

  const renderLinks = (coordinateSet: "desktop" | "mobile") =>
    edges.map((edge) => {
      const curve = curveFor(edge, coordinateSet);

      if (!curve) {
        return null;
      }

      return <path className={cn("fullscreen-risk-link", `risk-${edge.level}`)} d={curve} key={`${coordinateSet}-${edge.from}-${edge.to}`} />;
    });

  return (
    <div className="fullscreen-risk-graph" aria-label="Full-screen medicine supply chain risk graph">
      <svg aria-hidden className="fullscreen-risk-links" viewBox="0 0 100 100" preserveAspectRatio="none">
        <defs>
          <linearGradient id="fullscreen-risk-hot-link" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#ff5a0a" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#ff2d20" stopOpacity="0.86" />
          </linearGradient>
          <linearGradient id="fullscreen-risk-muted-link" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#858585" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#d0d0d0" stopOpacity="0.34" />
          </linearGradient>
        </defs>
        {renderLinks("desktop")}
      </svg>

      <svg
        aria-hidden
        className="fullscreen-risk-links fullscreen-risk-links-mobile"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="fullscreen-risk-hot-link-mobile" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#ff5a0a" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#ff2d20" stopOpacity="0.86" />
          </linearGradient>
          <linearGradient id="fullscreen-risk-muted-link-mobile" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#858585" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#d0d0d0" stopOpacity="0.34" />
          </linearGradient>
        </defs>
        {renderLinks("mobile")}
      </svg>

      {nodes.map((node) => (
        <button
          className={cn("fullscreen-risk-node", `risk-${node.level}`, `node-${node.kind}`)}
          key={node.id}
          style={
            {
              "--mobile-left": `${node.mobileX ?? node.x}%`,
              "--mobile-top": `${node.mobileY ?? node.y}%`,
              left: `${node.x}%`,
              top: `${node.y}%`,
            } as CSSProperties
          }
          type="button"
        >
          <span>{kindIcons[node.kind]}</span>
          <strong>{node.label}</strong>
          <small>{node.detail}</small>
          {node.metric ? <em>{node.metric}</em> : null}
        </button>
      ))}
    </div>
  );
}

export function RiskExplanationPanel() {
  return (
    <aside className="risk-explanation-panel">
      <div className="risk-score">
        <span>Risk score</span>
        <strong>87</strong>
        <p>Critical exposure</p>
      </div>

      <div className="risk-reason-list">
        <h3>Why this medicine is exposed</h3>
        <RiskReason level="critical" title="Single country dependency">
          API intermediate MPM-23 has 91% country concentration in India.
        </RiskReason>
        <RiskReason level="critical" title="Facility disruption">
          Gujarat flood alert intersects the only approved upstream facility.
        </RiskReason>
        <RiskReason level="elevated" title="Low substitute coverage">
          Two alternate suppliers exist, but neither is qualified for EU hospital tenders.
        </RiskReason>
      </div>
    </aside>
  );
}

function RiskReason({
  children,
  level,
  title,
}: {
  children: ReactNode;
  level: RiskLevel;
  title: string;
}) {
  return (
    <article className={cn("risk-reason", `risk-${level}`)}>
      <AlertTriangle aria-hidden size={16} />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </article>
  );
}

export function RiskSignalCard({
  children,
  meta,
  title,
}: {
  children: ReactNode;
  meta: string;
  title: string;
}) {
  return (
    <article className="risk-signal-card">
      <div>
        <RadioTower aria-hidden size={16} />
        <span>{meta}</span>
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      <a href="/dashboard">
        Open source <ArrowUpRight aria-hidden size={14} />
      </a>
    </article>
  );
}

export function ScenarioImpactPanel() {
  return (
    <section className="scenario-impact-panel">
      <div>
        <p>Scenario simulation</p>
        <h2>Gujarat flooding, port slowdowns, API intermediate shortage</h2>
      </div>

      <div className="scenario-impact-grid">
        <span>
          <strong>12</strong>
          medicines affected
        </span>
        <span>
          <strong>4</strong>
          hospitals below 21 days stock
        </span>
        <span>
          <strong>38%</strong>
          supplier capacity at risk
        </span>
      </div>
    </section>
  );
}
