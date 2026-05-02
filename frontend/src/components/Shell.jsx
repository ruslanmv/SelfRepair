import React from "react";

import { AdminAccountMenu } from "./AdminAccountMenu.jsx";
import { Icon } from "./atoms.jsx";

const ADMIN_USER = {
  name: "Ruslan M.",
  email: "admin@selfrepair.dev",
  initials: "RM",
  hue: 200,
};

const NAV = [
  { section: "Operate" },
  { id: "overview", label: "Overview", icon: "dashboard" },
  { id: "repos", label: "Repos", icon: "repos", count: "1.2k" },
  { id: "findings", label: "Findings", icon: "findings", count: 342 },
  { id: "repairs", label: "Repairs", icon: "repairs", count: 18 },
  { id: "issues", label: "Open Issues", icon: "findings", count: 7 },
  { id: "jobs", label: "Jobs", icon: "jobs", live: true },
  { section: "Govern" },
  { id: "policies", label: "Policies", icon: "policies" },
  { id: "audit", label: "Audit log", icon: "audit" },
  { section: "Configure" },
  { id: "settings", label: "Settings", icon: "settings" },
];

export const Sidebar = ({ route, onNav, onAccountAction }) => (
  // Three-region layout: head (logo + workspace) is fixed-height; nav is the
  // only scrollable region; footer (admin account) is fixed-height. This
  // prevents Settings from being clipped on short viewports and keeps the
  // account button from overlapping the nav list.
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
            <span>agent-matrix</span>
          </span>
          <Icon name="caretDown" s={12} style={{ color: "var(--fg-muted)" }} />
        </button>
      </div>
    </div>

    <nav className="sidebar-nav">
      {NAV.map((item, i) => {
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
            {item.live && (
              <span className="live" style={{ fontSize: 10 }}>
                2
              </span>
            )}
            {item.count != null && !item.live && (
              <span className="faint mono" style={{ fontSize: 11 }}>
                {item.count}
              </span>
            )}
          </div>
        );
      })}
    </nav>

    <div className="sidebar-footer">
      <AdminAccountMenu user={ADMIN_USER} onAction={onAccountAction} />
    </div>
  </aside>
);

export const Topbar = ({ crumbs = [], onCmd, right }) => (
  <header className="topbar">
    <div className="row gap-2 grow" style={{ minWidth: 0 }}>
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
    <button className="btn btn-ghost" onClick={onCmd} style={{ gap: 8 }}>
      <Icon name="search" s={13} />
      <span className="muted">Search · jump to anywhere</span>
      <span className="kbd" style={{ marginLeft: 8 }}>
        ⌘K
      </span>
    </button>
    {right}
    <button
      className="btn btn-icon btn-ghost"
      title="Notifications"
      style={{ position: "relative" }}
    >
      <Icon name="bell" s={14} />
      <span className="notif-dot" style={{ position: "absolute", top: 5, right: 5 }} />
    </button>
  </header>
);

const CMD_ITEMS = [
  { kind: "Page", label: "Overview", id: "overview", route: "overview" },
  { kind: "Page", label: "Repos", id: "repos", route: "repos" },
  { kind: "Page", label: "Findings", id: "findings", route: "findings" },
  { kind: "Page", label: "Repairs", id: "repairs", route: "repairs" },
  { kind: "Page", label: "Open Issues", id: "issues", route: "issues" },
  { kind: "Page", label: "Jobs", id: "jobs", route: "jobs" },
  { kind: "Page", label: "Policies", id: "policies", route: "policies" },
  { kind: "Page", label: "Audit log", id: "audit", route: "audit" },
  { kind: "Repo", label: "ruslanmv/SelfRepair", id: "R-1045", route: "repo", payload: "R-1045" },
  { kind: "Repo", label: "agent-matrix/matrix-hub", id: "R-1042", route: "repo", payload: "R-1042" },
  { kind: "Repo", label: "platform/payments-svc", id: "R-1048", route: "repo", payload: "R-1048" },
  { kind: "Repo", label: "ruslanmv/HomePilot", id: "R-1046", route: "repo", payload: "R-1046" },
  { kind: "Repair", label: "PR-2210 · Add pyproject.toml…", id: "PR-2210", route: "repair", payload: "PR-2210" },
  { kind: "Repair", label: "PR-2207 · LLM-assisted http.Client…", id: "PR-2207", route: "repair", payload: "PR-2207" },
  { kind: "Job", label: "J-77821 · live · ruslanmv/SelfRepair", id: "J-77821", route: "job", payload: "J-77821" },
  { kind: "Job", label: "J-77820 · live · platform/payments-svc", id: "J-77820", route: "job", payload: "J-77820" },
  { kind: "Action", label: "Suppress finding…", id: "act-suppress" },
  { kind: "Action", label: "Retry job…", id: "act-retry" },
  { kind: "Action", label: "Approve repair…", id: "act-approve" },
];

export const CommandPalette = ({ open, onClose, onPick }) => {
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
    if (!q.trim()) return CMD_ITEMS;
    const lq = q.toLowerCase();
    return CMD_ITEMS.filter(
      (i) => i.label.toLowerCase().includes(lq) || i.kind.toLowerCase().includes(lq),
    );
  }, [q]);

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
