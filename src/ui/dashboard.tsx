import { ChevronDown, Copy, Eye, Menu, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "#/lib/cn";
import { LogoMark } from "#/ui";

export function DashboardShell({
  children,
  detail,
  sidebar,
}: {
  children: ReactNode;
  detail: ReactNode;
  sidebar: ReactNode;
}) {
  return (
    <main className="dashboard-shell">
      <aside className="dashboard-sidebar">{sidebar}</aside>
      <section className="dashboard-main">{children}</section>
      <aside className="dashboard-detail">{detail}</aside>
    </main>
  );
}

export function DashboardSidebar({
  groups,
}: {
  groups: Array<{
    items: Array<{ isActive?: boolean; label: string }>;
    label: string;
  }>;
}) {
  return (
    <>
      <div className="dashboard-sidebar-brand">
        <LogoMark />
      </div>
      <nav aria-label="Dashboard navigation" className="dashboard-nav">
        {groups.map((group) => (
          <div className="dashboard-nav-group" key={group.label}>
            <p>{group.label}</p>
            {group.items.map((item) => (
              <a className={cn(item.isActive && "active")} href="/dashboard" key={item.label}>
                {item.label}
              </a>
            ))}
          </div>
        ))}
      </nav>
    </>
  );
}

export function DashboardTopbar({
  actions,
  eyebrow,
  title,
}: {
  actions?: ReactNode;
  eyebrow: string;
  title: string;
}) {
  return (
    <header className="dashboard-topbar">
      <div>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {actions ? <div className="dashboard-topbar-actions">{actions}</div> : null}
    </header>
  );
}

export function DashboardPanel({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <section className={cn("dashboard-panel", className)}>
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}

export type AppDashboardNavItem = {
  badge?: string;
  hasChevron?: boolean;
  href: string;
  icon: LucideIcon;
  isActive?: boolean;
  label: string;
  meta?: string;
};

export type AppDashboardNavSection = {
  items: AppDashboardNavItem[];
  label?: string;
};

export type AppDashboardBrand = {
  href?: string;
  mark?: ReactNode;
  name: string;
};

export type AppDashboardWorkspace = {
  initial: string;
  name: string;
};

export function AppDashboardMark() {
  return <span aria-hidden className="app-dashboard-flame" />;
}

export function AppDashboardShell({
  brand,
  children,
  footer,
  navSections,
  supportButton,
  topbar,
  workspace,
}: {
  brand: AppDashboardBrand;
  children: ReactNode;
  footer?: ReactNode;
  navSections: AppDashboardNavSection[];
  supportButton?: ReactNode;
  topbar?: ReactNode;
  workspace: AppDashboardWorkspace;
}) {
  return (
    <main className="app-dashboard-page">
      <div className="app-dashboard-frame">
        <AppDashboardSidebar brand={brand} footer={footer} navSections={navSections} />
        <section className="app-dashboard-app-shell" aria-label={`${brand.name} dashboard`}>
          {topbar ?? <AppDashboardTopbar workspace={workspace} />}
          {children}
          {supportButton ?? <AppDashboardSupportButton />}
        </section>
      </div>
    </main>
  );
}

export function AppDashboardSidebar({
  brand,
  footer,
  navSections,
}: {
  brand: AppDashboardBrand;
  footer?: ReactNode;
  navSections: AppDashboardNavSection[];
}) {
  return (
    <aside className="app-dashboard-sidebar" aria-label={`${brand.name} dashboard navigation`}>
      <a className="app-dashboard-sidebar-brand" href={brand.href ?? "/"}>
        {brand.mark ?? <AppDashboardMark />}
        <strong>{brand.name}</strong>
      </a>

      <nav className="app-dashboard-nav">
        {navSections.map((section) => (
          <div className="app-dashboard-nav-section" key={section.label ?? "primary"}>
            {section.label ? <p>{section.label}</p> : null}
            {section.items.map(({ badge, hasChevron, href, icon: Icon, isActive, label, meta }) => (
              <a
                className={cn(isActive && "active")}
                href={href}
                key={`${section.label ?? "primary"}-${label}`}
              >
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

      {footer}
    </aside>
  );
}

export function AppDashboardSidebarFooter({
  accountLabel,
  accountName,
  newsCount,
  newsLabel = "What's New",
}: {
  accountLabel: string;
  accountName: string;
  newsCount?: string;
  newsLabel?: string;
}) {
  return (
    <div className="app-dashboard-sidebar-footer">
      <button className="app-dashboard-news-button" type="button">
        <span>{newsLabel}</span>
        {newsCount ? <strong>{newsCount}</strong> : null}
      </button>

      <button className="app-dashboard-account-button" type="button">
        <span>{accountLabel}</span>
        <strong>{accountName}</strong>
      </button>

      <button className="app-dashboard-collapse-button" type="button">
        <ChevronDown aria-hidden size={20} />
        <span>Collapse</span>
      </button>
    </div>
  );
}

export function AppDashboardTopbar({
  actions,
  workspace,
}: {
  actions?: ReactNode;
  workspace: AppDashboardWorkspace;
}) {
  return (
    <header className="app-dashboard-topbar">
      <button className="app-dashboard-mobile-logo" type="button" aria-label="Open sidebar">
        <AppDashboardMark />
      </button>

      <button className="app-dashboard-team-switcher" type="button">
        <span>{workspace.initial}</span>
        <strong>{workspace.name}</strong>
        <ChevronDown aria-hidden size={18} />
      </button>

      <div className="app-dashboard-top-actions">
        {actions}
        <button className="app-dashboard-menu-button" type="button" aria-label="Open menu">
          <Menu aria-hidden size={24} />
        </button>
      </div>
    </header>
  );
}

export function AppDashboardIconButton({
  "aria-label": ariaLabel,
  badge,
  children,
  desktopOnly,
}: {
  "aria-label": string;
  badge?: string;
  children: ReactNode;
  desktopOnly?: boolean;
}) {
  return (
    <button
      aria-label={ariaLabel}
      className={cn(
        "app-dashboard-icon-button",
        badge && "has-badge",
        desktopOnly && "desktop-only",
      )}
      type="button"
    >
      {children}
      {badge ? <span>{badge}</span> : null}
    </button>
  );
}

export function AppDashboardAction({
  children,
  href,
  icon,
  isPrimary,
}: {
  children: ReactNode;
  href: string;
  icon?: ReactNode;
  isPrimary?: boolean;
}) {
  return (
    <a
      className={
        isPrimary
          ? "app-dashboard-upgrade-button desktop-only"
          : "app-dashboard-utility-button desktop-only"
      }
      href={href}
    >
      {icon}
      <span>{children}</span>
    </a>
  );
}

export function AppDashboardCanvas({ children }: { children: ReactNode }) {
  return <div className="app-dashboard-canvas">{children}</div>;
}

export type DashboardModule = {
  badge?: string;
  description: string;
  glyph: "crawl" | "interact" | "scrape" | "search";
  href: string;
  title: string;
};

export function DashboardModuleSection({
  modules,
  subtitle,
  title,
}: {
  modules: DashboardModule[];
  subtitle: string;
  title: string;
}) {
  return (
    <section className="app-dashboard-endpoints">
      <div className="app-dashboard-section-head">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>

      <div className="app-dashboard-endpoint-grid">
        {modules.map((module) => (
          <a className="app-dashboard-endpoint-card" href={module.href} key={module.title}>
            <span aria-hidden className={`endpoint-glyph ${module.glyph}`} />
            <div>
              <h2>
                {module.title}
                {module.badge ? <em>{module.badge}</em> : null}
              </h2>
              <p>{module.description}</p>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

export function AppDashboardSpacer() {
  return <div className="app-dashboard-spacer" aria-hidden />;
}

export function AppDashboardGrid({ children }: { children: ReactNode }) {
  return <section className="app-dashboard-grid">{children}</section>;
}

export function AppDashboardColumn({
  children,
  side,
}: {
  children: ReactNode;
  side: "left" | "right";
}) {
  return <div className={`app-dashboard-${side}-column`}>{children}</div>;
}

export function AppDashboardPanel({
  children,
  className,
  metric,
  subtitle,
  title,
}: {
  children?: ReactNode;
  className?: string;
  metric?: string;
  subtitle?: string;
  title: ReactNode;
}) {
  return (
    <article className={cn("app-dashboard-panel", className)}>
      <header>
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {metric ? <strong>{metric}</strong> : null}
      </header>
      {children}
    </article>
  );
}

export function DashboardLineChart({ labels }: { labels: string[] }) {
  return (
    <div className="app-dashboard-chart" aria-label="Template activity chart">
      <span />
      <div>
        {labels.map((label) => (
          <small key={label}>{label}</small>
        ))}
      </div>
    </div>
  );
}

export function DashboardCapacity({ label, value }: { label: string; value: string }) {
  return (
    <div className="browser-count">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function DashboardTokenPanel({ href, token }: { href: string; token: string }) {
  return (
    <article className="app-dashboard-panel token-panel">
      <a href={href}>
        <h2>Access token</h2>
        <p>Connect apps and automation safely</p>
      </a>
      <div className="token-field">
        <code>{token}</code>
        <button type="button" aria-label="Show access token">
          <Eye aria-hidden size={18} />
        </button>
        <button type="button" aria-label="Copy access token">
          <Copy aria-hidden size={18} />
        </button>
      </div>
    </article>
  );
}

export function DashboardAgentIntegrationPanel({
  command,
  config,
}: {
  command: ReactNode;
  config: string;
}) {
  return (
    <article className="app-dashboard-panel integrations-panel">
      <header>
        <div>
          <h2>Agent Integration</h2>
          <p>Give future agents the context and primitives they should use</p>
        </div>
        <div className="integration-tabs" aria-hidden>
          <span />
          <span />
          <span />
        </div>
      </header>

      <div className="integration-card">
        <Copy aria-hidden size={22} />
        <div>
          <strong>
            Dashboard kit <small>Use first</small>
          </strong>
          <p>Import from #/ui/dashboard before building a new app surface</p>
        </div>
        <button type="button">
          <Copy aria-hidden size={18} />
          <span>Copy</span>
        </button>
      </div>

      <div className="agent-note-card">
        <p>Import</p>
        <code>{command}</code>
        <p>Agent note</p>
        <pre>{config}</pre>
      </div>
    </article>
  );
}

export function AppDashboardSupportButton() {
  return (
    <button className="app-dashboard-chat" type="button" aria-label="Open support chat">
      <span />
      <span />
      <span />
    </button>
  );
}
