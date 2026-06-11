import React from "react";

import { AdminAccountMenu } from "./AdminAccountMenu.jsx";
import { Icon } from "./atoms.jsx";
import { NotificationBell } from "./NotificationBell.jsx";

const FALLBACK_USER = {
  name: "SelfRepair user",
  email: "",
  initials: "SR",
  hue: 200,
};

const NAV = [
  { section: "Operate" },
  { id: "overview", label: "Overview", icon: "dashboard" },
  { id: "inbox", label: "Inbox", icon: "findings" },
  { id: "repos", label: "Repos", icon: "repos" },
  { id: "findings", label: "Findings", icon: "findings" },
  { id: "repairs", label: "Repairs", icon: "repairs" },
  { id: "issues", label: "Open Issues", icon: "findings" },
  { id: "jobs", label: "Jobs", icon: "jobs" },
  { section: "Govern" },
  { id: "policies", label: "Policies", icon: "policies" },
  { id: "audit", label: "Audit log", icon: "audit" },
  { section: "Configure" },
  { id: "connections", label: "Connections", icon: "branch" },
  { id: "settings", label: "Settings", icon: "settings" },
  { section: "Admin", admin: true },
  { id: "admin-users", label: "Users", icon: "shield", admin: true },
  { id: "admin-system", label: "System", icon: "dashboard", admin: true },
  { id: "admin-logs", label: "Logs", icon: "audit", admin: true },
];

// Real, live nav badges: only render a count when the backend reports a
// positive number (no fabricated placeholder values).
const NavBadge = ({ value }) => {
  if (value == null || value === 0) return null;
  const display = typeof value === "number" && value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value;
  return (
    <span className="faint mono" style={{ fontSize: 11 }}>
      {display}
    </span>
  );
};

export const Sidebar = ({ route, onNav, onAccountAction, user, onClose, counts = {}, workspace = "agent-matrix", isAdmin = false }) => (
  // Three-region layout: head (logo + workspace) is fixed-height; nav is the
  // only scrollable region; footer (admin account) is fixed-height.
  <aside className="sidebar">
    <div className="sidebar-head">
      <div className="row" style={{ alignItems: "center", gap: 10, padding: "14px 16px 12px" }}>
        <span className="brandmark">
          <span className="check">
            <svg viewBox="0 0 24 24" fill="none" stroke="#0A0E27" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12.5l4.5 4.5L19 7" />
            </svg>
          </span>
        </span>
        <div className="col" style={{ lineHeight: 1.15 }}>
          <span style={{ fontWeight: 700, letterSpacing: "-0.01em" }}>SelfRepair</span>
          <span
            className="faint"
            style={{ fontSize: 10.5, letterSpacing: "0.06em", textTransform: "uppercase" }}
          >
            Console · v1.0
          </span>
        </div>
        {/* Mobile-only: close the drawer. */}
        <button className="sidebar-close" aria-label="Close menu" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      <div style={{ padding: "0 12px 8px" }}>
        <button className="btn" style={{ width: "100%", justifyContent: "space-between", height: 30 }}>
          <span className="row gap-2">
            <span
              style={{
                width: 14,
                height: 14,
                borderRadius: 3,
                background: "linear-gradient(135deg, #8B5CF6, #06B6D4)",
              }}
            />
            <span>{workspace}</span>
          </span>
          <Icon name="caretDown" s={12} style={{ color: "var(--fg-muted)" }} />
        </button>
      </div>
    </div>

    <nav className="sidebar-nav">
      {NAV.filter((item) => !item.admin || isAdmin).map((item, i) => {
        if (item.section)
          return (
            <div key={`s${i}`} className="nav-section">
              {item.section}
            </div>
          );
        const active = route === item.id;
        return (
          <div
            key={item.id}
            className={`nav-item ${active ? "is-active" : ""}`}
            onClick={() => onNav(item.id)}
          >
            <span className="nav-ico">
              <Icon name={item.icon} s={15} />
            </span>
            <span style={{ flex: 1 }}>{item.label}</span>
            <NavBadge value={counts[item.id]} />
          </div>
        );
      })}
    </nav>

    <div className="sidebar-footer">
      <AdminAccountMenu user={user || FALLBACK_USER} onAction={onAccountAction} />
    </div>
  </aside>
);

export const Topbar = ({ crumbs = [], onCmd, onMenu, right, onNav }) => (
  <header className="topbar">
    {/* Mobile-only hamburger to open the nav drawer. */}
    <button className="nav-toggle" aria-label="Open menu" onClick={onMenu}>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M3 6h18M3 12h18M3 18h18" />
      </svg>
    </button>
    <div className="row gap-2 grow topbar-crumbs" style={{ minWidth: 0 }}>
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          {i > 0 && (
            <Icon name="caret" s={12} style={{ color: "var(--fg-faint)" }} />
          )}
          <span
            style={{
              fontSize: "var(--t-13)",
              color: i === crumbs.length - 1 ? "var(--fg)" : "var(--fg-muted)",
              fontWeight: i === crumbs.length - 1 ? 600 : 500,
              cursor: c.onClick ? "pointer" : "default",
            }}
            onClick={c.onClick}
          >
            {c.label}
          </span>
        </React.Fragment>
      ))}
    </div>
    <button className="btn btn-ghost topbar-search" onClick={onCmd} style={{ gap: 8 }} aria-label="Search">
      <Icon name="search" s={13} />
      <span className="muted topbar-search-label">Search · jump to anywhere</span>
      <span className="kbd" style={{ marginLeft: 8 }}>
        ⌘K
      </span>
    </button>
    {right}
    <NotificationBell onNav={onNav} />
  </header>
);

const CMD_ITEMS = [
  { kind: "Page", label: "Overview", id: "overview", route: "overview" },
  { kind: "Page", label: "Inbox", id: "inbox", route: "inbox" },
  { kind: "Page", label: "Repos", id: "repos", route: "repos" },
  { kind: "Page", label: "Findings", id: "findings", route: "findings" },
  { kind: "Page", label: "Repairs", id: "repairs", route: "repairs" },
  { kind: "Page", label: "Open Issues", id: "issues", route: "issues" },
  { kind: "Page", label: "Jobs", id: "jobs", route: "jobs" },
  { kind: "Page", label: "Policies", id: "policies", route: "policies" },
  { kind: "Page", label: "Audit log", id: "audit", route: "audit" },
  { kind: "Page", label: "Connections", id: "connections", route: "connections" },
  { kind: "Page", label: "Settings", id: "settings", route: "settings" },
  { kind: "Admin", label: "Users", id: "admin-users", route: "admin-users", admin: true },
  { kind: "Admin", label: "System", id: "admin-system", route: "admin-system", admin: true },
  { kind: "Admin", label: "Logs", id: "admin-logs", route: "admin-logs", admin: true },
];

export const CommandPalette = ({ open, onClose, onPick, isAdmin = false }) => {
  const [q, setQ] = React.useState("");
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const items = React.useMemo(() => {
    const base = CMD_ITEMS.filter((i) => !i.admin || isAdmin);
    if (!q.trim()) return base;
    const lq = q.toLowerCase();
    return base.filter(
      (i) => i.label.toLowerCase().includes(lq) || i.kind.toLowerCase().includes(lq),
    );
  }, [q, isAdmin]);

  const onKey = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(items.length - 1, a + 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (items[active]) {
        onPick(items[active]);
        onClose();
      }
    }
    if (e.key === "Escape") onClose();
  };

  if (!open) return null;
  return (
    <div className="cmd-overlay" onClick={onClose}>
      <div className="cmd" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cmd-input"
          placeholder="Search repos, findings, jobs… or type a command"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
        />
        <div className="cmd-list">
          {items.length === 0 && (
            <div
              style={{
                padding: 24,
                textAlign: "center",
                color: "var(--fg-faint)",
                fontSize: "var(--t-13)",
              }}
            >
              No matches
            </div>
          )}
          {items.map((it, i) => (
            <div
              key={it.id}
              className={`cmd-row ${i === active ? "is-active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => {
                onPick(it);
                onClose();
              }}
            >
              <span className="cmd-kind" style={{ width: 60 }}>
                {it.kind}
              </span>
              <span style={{ flex: 1 }}>{it.label}</span>
              {i === active && <span className="kbd">↵</span>}
            </div>
          ))}
        </div>
        <div
          className="hairline-t"
          style={{
            padding: "8px 14px",
            display: "flex",
            gap: 16,
            fontSize: 11,
            color: "var(--fg-faint)",
          }}
        >
          <span>
            <span className="kbd">↑↓</span> navigate
          </span>
          <span>
            <span className="kbd">↵</span> select
          </span>
          <span>
            <span className="kbd">esc</span> close
          </span>
        </div>
      </div>
    </div>
  );
};
