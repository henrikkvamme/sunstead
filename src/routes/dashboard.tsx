import { createFileRoute } from "@tanstack/react-router";
import {
  BarChart3,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Home,
  KeyRound,
  List,
  MoreVertical,
  Play,
  User,
} from "lucide-react";

export const Route = createFileRoute("/dashboard")({
  component: Dashboard,
});

const navItems = [
  { icon: Home, label: "Overview" },
  { icon: Play, label: "Playground" },
  { icon: List, isActive: true, label: "Activity Logs" },
  { icon: BarChart3, label: "Usage" },
  { icon: KeyRound, label: "API Keys" },
  { icon: User, label: "Account" },
];

const rows = [
  {
    count: "1",
    date: "July 26,\n2024 at\nAM",
    expanded: true,
    method: "/crawl",
    source: "Playground",
    status: "success",
    time: "7.185s",
    url: "https://phys.org/news/2024-07-pongamia-trees-ci...",
  },
  {
    count: "4",
    date: "July 26,\n2024 at\nAM",
    method: "/crawl",
    source: "Playground",
    url: "https://www.crewai.com/",
  },
  {
    count: "2",
    date: "July 26,\n2024 at\nAM",
    method: "/scrape",
    source: "API",
    url: "https://docs.firecrawl.dev/",
  },
];

const stages = [
  { color: "blue", label: "Queue job is waiting", meta: "AM" },
  { color: "blue", label: "Queue job is active", meta: "AM" },
  {
    color: "green",
    isResult: true,
    label: "https://phys.org/news/2024-07-pongamia-trees-ci...",
    meta: "AM | method: scrapingBee | success | 3780ms | worker: e2867524f70798",
  },
  { color: "green", label: "Queue job is completed", meta: "AM" },
];

function Dashboard() {
  return (
    <main className="firecrawl-dashboard-page">
      <div className="firecrawl-dashboard-frame">
        <aside className="firecrawl-sidebar">
          <a className="firecrawl-sidebar-brand" href="/">
            <span aria-hidden>🔥</span>
            <strong>Firecrawl</strong>
          </a>

          <nav aria-label="Dashboard navigation" className="firecrawl-dashboard-nav">
            {navItems.map(({ icon: Icon, isActive, label }) => (
              <a className={isActive ? "active" : undefined} href="/dashboard" key={label}>
                <Icon aria-hidden size={18} strokeWidth={1.9} />
                <span>{label}</span>
              </a>
            ))}
          </nav>

          <div className="firecrawl-alpha-card">
            <strong>Dashboard is in Alpha</strong>
            <p>
              Please reach out to us at <span /> if you have any feedback.
            </p>
          </div>

          <div className="firecrawl-account">
            <span>E</span>
            <strong>Eric Ciarla</strong>
            <button aria-label="Open account menu" type="button">
              <MoreVertical aria-hidden size={18} />
            </button>
          </div>
        </aside>

        <section aria-label="Activity Logs" className="firecrawl-activity">
          <div className="activity-table">
            {rows.map((row) => (
              <article className="activity-row" key={row.url}>
                <header className="activity-row-header">
                  <button aria-label={row.expanded ? "Collapse log" : "Expand log"} type="button">
                    {row.expanded ? (
                      <ChevronDown aria-hidden size={19} />
                    ) : (
                      <ChevronRight aria-hidden size={19} />
                    )}
                  </button>
                  <span className="activity-url">{row.url}</span>
                  <span className="activity-method">{row.method}</span>
                  <span className="activity-count">{row.count}</span>
                  <span className="activity-date">{row.date}</span>
                  <span className="activity-source">{row.source}</span>
                  <button aria-label="Download log" className="download-button" type="button">
                    <Download aria-hidden size={18} />
                  </button>
                </header>

                {row.expanded ? (
                  <div className="activity-expanded">
                    <div className="activity-meta">
                      <span>crawl</span>
                      <span>•</span>
                      <span>id:</span>
                      <span className="meta-spacer" />
                      <span>•</span>
                      <span>{row.time}</span>
                      <span>•</span>
                      <span>{row.status}</span>
                    </div>

                    <div className="queue-timeline">
                      {stages.map((stage) => (
                        <section className="queue-card" key={stage.label}>
                          <span className={`queue-dot ${stage.color}`} />
                          <div>
                            <strong>{stage.label}</strong>
                            {stage.isResult ? (
                              <a aria-label="Open scraped page" href="/dashboard">
                                <ExternalLink aria-hidden size={15} />
                              </a>
                            ) : null}
                            <p>{stage.meta}</p>
                          </div>
                          <ChevronDown aria-hidden className="queue-chevron" size={19} />
                        </section>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>

        <button aria-label="Open support chat" className="firecrawl-chat" type="button">
          <span />
        </button>
      </div>
    </main>
  );
}
