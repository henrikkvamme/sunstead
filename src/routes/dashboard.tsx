import { createFileRoute } from "@tanstack/react-router";
import { ArrowRight, Code2, Plus, Search, ShieldCheck } from "lucide-react";

import { Button } from "#/ui";
import { DashboardPanel, DashboardShell, DashboardSidebar, DashboardTopbar } from "#/ui/dashboard";

export const Route = createFileRoute("/dashboard")({
  component: Dashboard,
});

const navGroups = [
  {
    label: "Workspace",
    items: [
      { label: "Overview", isActive: true },
      { label: "Playground" },
      { label: "Jobs" },
      { label: "Sources" },
    ],
  },
  {
    label: "Build",
    items: [
      { label: "API keys" },
      { label: "Webhooks" },
      { label: "Usage" },
      { label: "Settings" },
    ],
  },
];

const metrics = [
  ["Requests", "24.8K", "+12.4%"],
  ["Success rate", "99.2%", "+0.8%"],
  ["Avg latency", "1.4s", "-240ms"],
  ["Credits used", "68%", "12.4K left"],
];

function Dashboard() {
  return (
    <DashboardShell
      sidebar={<DashboardSidebar groups={navGroups} />}
      detail={
        <div className="dashboard-detail-inner">
          <div className="detail-status">
            <ShieldCheck aria-hidden size={18} />
            <span>System healthy</span>
          </div>
          <DashboardPanel title="Selected job">
            <div className="detail-empty">
              <Code2 aria-hidden size={22} />
              <p>Select a crawl to preview markdown, JSON, screenshots, and metadata.</p>
            </div>
          </DashboardPanel>
        </div>
      }
    >
      <DashboardTopbar
        eyebrow="Production workspace"
        title="Dashboard"
        actions={
          <>
            <a className="dashboard-search" href="/dashboard">
              <Search aria-hidden size={16} />
              Search jobs...
            </a>
            <Button
              href="/dashboard"
              icon={<Plus aria-hidden size={16} />}
              size="sm"
              variant="primary"
            >
              New crawl
            </Button>
          </>
        }
      />

      <div className="dashboard-metrics">
        {metrics.map(([label, value, delta]) => (
          <DashboardPanel className="metric-panel" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{delta}</small>
          </DashboardPanel>
        ))}
      </div>

      <DashboardPanel className="dashboard-builder" title="Start a crawl">
        <div className="builder-tabs" aria-label="Crawl modes">
          <button className="active" type="button">
            Scrape
          </button>
          <button type="button">Search</button>
          <button type="button">Map</button>
          <button type="button">Crawl</button>
        </div>
        <div className="builder-input">
          <span>https://</span>
          <strong>example.com</strong>
          <Button href="/dashboard" size="sm" variant="primary">
            Start
          </Button>
        </div>
      </DashboardPanel>

      <DashboardPanel title="Recent activity">
        <div className="activity-list">
          {["docs.firecrawl.dev", "example.com/pricing", "status.example.com"].map((source) => (
            <a href="/dashboard" key={source}>
              <span>{source}</span>
              <small>Scrape complete</small>
              <ArrowRight aria-hidden size={15} />
            </a>
          ))}
        </div>
      </DashboardPanel>
    </DashboardShell>
  );
}
