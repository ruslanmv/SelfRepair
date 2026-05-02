import React from "react";

import { HealthBar, Icon, RepoIcon } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const AutoRepairModal = ({ open, onClose, onLaunch }) => {
  const [selected, setSelected] = React.useState(new Set(["R-1045", "R-1046"]));
  const [policy, setPolicy] = React.useState("conservative");
  const [schedule, setSchedule] = React.useState("on-push");
  const [search, setSearch] = React.useState("");

  if (!open) return null;
  const repos = D.repos.filter((r) => !search || r.name.toLowerCase().includes(search.toLowerCase()));
  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const toggleAll = () => {
    if (selected.size === repos.length) setSelected(new Set());
    else setSelected(new Set(repos.map((r) => r.id)));
  };

  return (
    <div className="cmd-overlay" onClick={onClose} style={{ paddingTop: "8vh" }}>
      <div className="run-modal" onClick={(e) => e.stopPropagation()} style={{ width: 720 }}>
        <div className="run-head">
          <div className="row gap-3">
            <span
              style={{
                width: 28,
                height: 28,
                borderRadius: 7,
                background: "var(--grad-brand)",
                display: "grid",
                placeItems: "center",
                boxShadow: "0 4px 12px rgba(139,92,246,0.25)",
              }}
            >
              <Icon name="repairs" s={14} style={{ color: "white" }} />
            </span>
            <div className="col">
              <h2 style={{ margin: 0, fontSize: "var(--t-16)", fontWeight: 600 }}>Auto-repair mode</h2>
              <span className="muted" style={{ fontSize: "var(--t-12)" }}>Continuously runs repair on selected repos under a policy</span>
            </div>
          </div>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--hairline)" }}>
          <div className="muted" style={{ fontSize: "var(--t-12)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Policy</div>
          <div className="strategy-grid">
            {[
              { id: "conservative", label: "Conservative", desc: "auto-fix only · human approval · no auto-merge", tone: "ok", icon: "shield" },
              { id: "balanced",     label: "Balanced",     desc: "auto-fix + LLM-assist · human approval", tone: "info", icon: "spark" },
              { id: "aggressive",   label: "Aggressive",   desc: "all strategies · auto-merge if green", tone: "warn", icon: "play" },
            ].map((p) => (
              <div key={p.id} className={`strategy-card ${policy === p.id ? "is-active" : ""}`} onClick={() => setPolicy(p.id)}>
                <span className="strategy-ico" style={{ background: `var(--${p.tone}-bg)`, color: `var(--${p.tone})`, borderColor: `var(--${p.tone}-border)` }}>
                  <Icon name={p.icon} s={14} />
                </span>
                <div className="col grow"><span style={{ fontSize: "var(--t-13)", fontWeight: 600 }}>{p.label}</span><span className="faint" style={{ fontSize: "var(--t-12)" }}>{p.desc}</span></div>
                <span className={`radio ${policy === p.id ? "is-on" : ""}`} />
              </div>
            ))}
          </div>

          <div className="row gap-2" style={{ marginTop: 14 }}>
            <span className="muted" style={{ fontSize: "var(--t-12)" }}>Schedule:</span>
            {[
              { id: "on-push", label: "On push" },
              { id: "hourly", label: "Hourly" },
              { id: "daily", label: "Daily 02:00 UTC" },
              { id: "manual", label: "Manual only" },
            ].map((s) => (
              <span key={s.id} className={`chip ${schedule === s.id ? "is-active" : ""}`} onClick={() => setSchedule(s.id)}>{s.label}</span>
            ))}
          </div>
        </div>

        <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--hairline)" }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <div className="muted" style={{ fontSize: "var(--t-12)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Selected repos · {selected.size} of {repos.length}</div>
            <a className="muted" style={{ cursor: "pointer", color: "var(--cyan)", fontSize: "var(--t-12)" }} onClick={toggleAll}>{selected.size === repos.length ? "Deselect all" : "Select all"}</a>
          </div>
          <div style={{ position: "relative", marginBottom: 8 }}>
            <Icon name="search" s={12} style={{ position: "absolute", left: 9, top: 8, color: "var(--fg-faint)" }} />
            <input
              className="input"
              placeholder="Filter repos…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: "100%", paddingLeft: 26 }}
            />
          </div>
          <div style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--hairline)", borderRadius: 6 }}>
            {repos.map((r) => (
              <label key={r.id} className="row gap-3 repo-pick-row" style={{ padding: "8px 12px", borderBottom: "1px solid var(--hairline)", cursor: "pointer" }}>
                <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                <RepoIcon platform={r.platform} s={12} />
                <span style={{ flex: 1, fontSize: "var(--t-13)" }}>{r.name}</span>
                <HealthBar value={r.health} />
                <span className="faint mono" style={{ fontSize: "var(--t-12)", width: 60, textAlign: "right" }}>{r.openFindings} find</span>
              </label>
            ))}
          </div>
        </div>

        <div className="run-foot">
          <span className="muted" style={{ fontSize: "var(--t-12)" }}>
            Will scan <b>{selected.size}</b> repos · est. <b className="mono">~{(selected.size * 1.4).toFixed(1)}s</b> per cycle · est. token spend <b className="mono">~${(selected.size * 0.018).toFixed(3)}</b>/run
          </span>
          <div className="row gap-2">
            <button className="btn" onClick={onClose}>Cancel</button>
            <button
              className="btn btn-primary"
              onClick={() => {
                onLaunch?.({ repos: [...selected], policy, schedule });
                onClose();
              }}
            >
              <Icon name="play" s={12} /> Enable auto-repair
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
