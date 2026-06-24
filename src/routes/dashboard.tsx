import { createFileRoute } from "@tanstack/react-router";
import {
  BarChart3,
  Bell,
  BookOpen,
  ChevronDown,
  Copy,
  Eye,
  FileText,
  HelpCircle,
  Home,
  KeyRound,
  List,
  Menu,
  Monitor,
  Paperclip,
  Search,
  Settings,
  Sparkles,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

export const Route = createFileRoute("/dashboard")({
  component: Dashboard,
});

type NavItem = {
  badge?: string;
  hasChevron?: boolean;
  href: string;
  icon: LucideIcon;
  isActive?: boolean;
  label: string;
  meta?: string;
};

type NavSection = {
  items: NavItem[];
  label?: string;
};

const navSections: NavSection[] = [
  {
    items: [{ href: "/dashboard", icon: Home, isActive: true, label: "Overview" }],
  },
  {
    label: "WHAT'S NEW",
    items: [{ badge: "NEW", href: "/dashboard", icon: Waypoints, label: "Monitor the web" }],
  },
  {
    label: "PLAYGROUND",
    items: [
      { href: "/dashboard", icon: Search, label: "Search the web", meta: "/search" },
      { href: "/dashboard", icon: FileText, label: "Scrape a web page", meta: "/scrape" },
      { href: "/dashboard", icon: Sparkles, label: "Interact with a page", meta: "/interact" },
      { href: "/dashboard", icon: Paperclip, label: "Parse a file", meta: "/parse" },
      { hasChevron: true, href: "/dashboard", icon: Waypoints, label: "Crawl entire website" },
    ],
  },
  {
    label: "RESEARCH PREVIEW",
    items: [{ href: "/dashboard", icon: Sparkles, label: "Agent", meta: "/agent" }],
  },
  {
    label: "ACCOUNT",
    items: [
      { href: "/dashboard", icon: List, label: "Activity Logs" },
      { href: "/dashboard", icon: BarChart3, label: "Usage" },
      { href: "/dashboard", icon: KeyRound, label: "API Keys" },
      { href: "/dashboard", icon: Settings, label: "Settings" },
    ],
  },
];

const endpoints = [
  {
    copy: "Search the web and get full content from results.",
    glyph: "search",
    label: "Search",
  },
  {
    copy: "Get llm-ready data from websites. Markdown, JSON, screenshot, etc.",
    glyph: "scrape",
    label: "Scrape",
  },
  {
    badge: "NEW",
    copy: "Interact with a scraped page using AI prompts or code.",
    glyph: "interact",
    label: "Interact",
  },
  {
    copy: "Crawl all the pages on a website and get data for each page.",
    glyph: "crawl",
    label: "Crawl",
  },
];

function Dashboard() {
  return (
    <main className="firecrawl-dashboard-page">
      <div className="firecrawl-dashboard-frame">
        <aside className="firecrawl-sidebar" aria-label="Firecrawl dashboard navigation">
          <a className="firecrawl-sidebar-brand" href="/">
            <span aria-hidden className="firecrawl-flame" />
            <strong>Firecrawl</strong>
          </a>

          <nav className="firecrawl-dashboard-nav">
            {navSections.map((section) => (
              <div className="firecrawl-nav-section" key={section.label ?? "overview"}>
                {section.label ? <p>{section.label}</p> : null}
                {section.items.map(({ badge, hasChevron, href, icon: Icon, isActive, label, meta }) => (
                  <a className={isActive ? "active" : undefined} href={href} key={label}>
                    <Icon aria-hidden size={17} strokeWidth={1.9} />
                    <span>
                      {label}
                      {meta ? <small>{meta}</small> : null}
                    </span>
                    {badge ? <em>{badge}</em> : null}
                    {hasChevron ? <ChevronDown aria-hidden className="nav-chevron" size={14} /> : null}
                  </a>
                ))}
              </div>
            ))}
          </nav>

          <div className="firecrawl-sidebar-footer">
            <button className="firecrawl-news-button" type="button">
              <span>What's New</span>
              <strong>31</strong>
            </button>

            <button className="firecrawl-account-button" type="button">
              <span>HK</span>
              <strong>henrik@example.com</strong>
            </button>

            <button className="firecrawl-collapse-button" type="button">
              <ChevronDown aria-hidden size={20} />
              <span>Collapse</span>
            </button>
          </div>
        </aside>

        <section className="firecrawl-app-shell" aria-label="Firecrawl dashboard overview">
          <header className="firecrawl-topbar">
            <button className="firecrawl-mobile-logo" type="button" aria-label="Open sidebar">
              <span aria-hidden className="firecrawl-flame" />
            </button>

            <button className="firecrawl-team-switcher" type="button">
              <span>P</span>
              <strong>Personal Team</strong>
              <ChevronDown aria-hidden size={18} />
            </button>

            <div className="firecrawl-top-actions">
              <button className="firecrawl-icon-button has-badge" type="button" aria-label="Notifications">
                <Bell aria-hidden size={19} />
                <span>1</span>
              </button>
              <button className="firecrawl-icon-button desktop-only" type="button" aria-label="Switch theme">
                <Monitor aria-hidden size={20} />
              </button>
              <button className="firecrawl-utility-button desktop-only" type="button">
                <HelpCircle aria-hidden size={18} />
                <span>Help</span>
              </button>
              <a className="firecrawl-utility-button desktop-only" href="/dashboard">
                <BookOpen aria-hidden size={18} />
                <span>Docs</span>
              </a>
              <a className="firecrawl-upgrade-button desktop-only" href="/dashboard">
                <KeyRound aria-hidden size={17} />
                <span>Upgrade</span>
              </a>
              <button className="firecrawl-menu-button" type="button" aria-label="Open menu">
                <Menu aria-hidden size={24} />
              </button>
            </div>
          </header>

          <div className="firecrawl-dashboard-canvas">
            <section className="firecrawl-endpoints">
              <div className="firecrawl-section-head">
                <h1>Explore our endpoints</h1>
                <p>Power your applications with our comprehensive scraping API</p>
              </div>

              <div className="firecrawl-endpoint-grid">
                {endpoints.map((endpoint) => (
                  <a className="firecrawl-endpoint-card" href="/dashboard" key={endpoint.label}>
                    <span aria-hidden className={`endpoint-glyph ${endpoint.glyph}`} />
                    <div>
                      <h2>
                        {endpoint.label}
                        {endpoint.badge ? <em>{endpoint.badge}</em> : null}
                      </h2>
                      <p>{endpoint.copy}</p>
                    </div>
                  </a>
                ))}
              </div>
            </section>

            <div className="firecrawl-dashboard-spacer" aria-hidden />

            <section className="firecrawl-dashboard-grid">
              <div className="firecrawl-left-column">
                <article className="firecrawl-panel chart-panel">
                  <header>
                    <div>
                      <h2>Scraped pages - Last 7 days</h2>
                      <p>Credit usage differs</p>
                    </div>
                    <strong>0</strong>
                  </header>

                  <div className="firecrawl-chart" aria-label="No scraped pages in the last 7 days">
                    <span />
                    <div>
                      <small>06/18</small>
                      <small>06/21</small>
                      <small>06/24</small>
                    </div>
                  </div>
                </article>

                <article className="firecrawl-panel browser-panel">
                  <header>
                    <div>
                      <h2>
                        Concurrent Browsers <em>[ LIVE ]</em>
                      </h2>
                      <p># of active browsers, upgrade plan for faster scraping</p>
                    </div>
                  </header>
                  <div className="browser-count">
                    <strong>0</strong>
                    <span>of 2 active browsers</span>
                  </div>
                </article>
              </div>

              <div className="firecrawl-right-column">
                <article className="firecrawl-panel api-key-panel">
                  <a href="/dashboard">
                    <h2>API Key</h2>
                    <p>Start scraping right away</p>
                  </a>
                  <div className="api-key-field">
                    <code>fc-6***********************3d40</code>
                    <button type="button" aria-label="Show API key">
                      <Eye aria-hidden size={18} />
                    </button>
                    <button type="button" aria-label="Copy API key">
                      <Copy aria-hidden size={18} />
                    </button>
                  </div>
                </article>

                <article className="firecrawl-panel integrations-panel">
                  <header>
                    <div>
                      <h2>Agent Integrations</h2>
                      <p>Give your AI agents web data</p>
                    </div>
                    <div className="integration-tabs" aria-hidden>
                      <span />
                      <span />
                      <span />
                    </div>
                  </header>

                  <div className="skill-card">
                    <FileText aria-hidden size={22} />
                    <div>
                      <strong>
                        SKILL.md <small>View</small>
                      </strong>
                      <p>Paste into your AI agent's context</p>
                    </div>
                    <button type="button">
                      <Copy aria-hidden size={18} />
                      <span>Copy</span>
                    </button>
                  </div>

                  <div className="cli-card">
                    <p>CLI</p>
                    <code>
                      $ npx -y firecrawl-cli init <span>--all --browser</span>
                    </code>
                    <p>MCP Config</p>
                    <pre>{`{
  "mcpServers": {
    "firecrawl-mcp": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "$API_KEY"
      }
    }
  }
}`}</pre>
                  </div>
                </article>
              </div>
            </section>
          </div>

          <button className="firecrawl-chat" type="button" aria-label="Open support chat">
            <span />
            <span />
            <span />
          </button>
        </section>
      </div>
    </main>
  );
}
