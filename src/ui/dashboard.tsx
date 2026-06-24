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
