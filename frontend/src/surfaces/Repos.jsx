import React from "react";

import { HealthBar, Icon, RepoIcon, SeverityDot, Sparkline } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const Repos = ({ onNav, layout = "table" }) => {
  const [q, setQ] = React.useState("");
  const [platform, setPlatform] = React.useState("all");
  const [healthFilter, setHealthFilter] = React.useState("all");

  const filtered = D.repos.filter((r) => {
    if (q && !r.name.toLowerCase().includes(q.toLowerCase())) return false;
    if (platform !== "all" && r.platform !== platform) return false;
    if (healthFilter === "low" && r.health >= 70) return false;
    if (healthFilter === "high" && r.health < 85) return false;
    return true;
  });

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", letterSpacing: "-0.01em", fontWeight: 600 }}>Repos</h1>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
            {D.repos.length} of 1,284 · server-paginated
          </p>
        </div>
        <div className="row gap-2">
          <div className="seg">
            <button className={layout === "table" ? "is-active" : ""}>Table</button>
            <button className={layout === "cards" ? "is-active" : ""}>Cards</button>
            <button className={layout === "tree" ? "is-active" : ""}>Tree</button>
          </div>
          <button className="btn"><Icon name="filter" s={13} /> Saved views</button>
          <button className="btn btn-primary"><Icon name="plus" s={13} /> Connect repo</button>
        </div>
      </div>

      <div className="row gap-2" style={{ marginBottom: 10, flexWrap: "wrap" }}>
        <div style={{ position: "relative" }}>
          <Icon name="search" s={13} style={{ position: "absolute", left: 9, top: 8, color: "var(--fg-faint)" }} />
          <input className="input" placeholder="Search repos…" value={q} onChange={(e) => setQ(e.target.value)} style={{ paddingLeft: 28, width: 240 }} />
        </div>
        <span className={`chip ${platform === "all" ? "is-active" : ""}`} onClick={() => setPlatform("all")}>All platforms</span>
        <span className={`chip ${platform === "github" ? "is-active" : ""}`} onClick={() => setPlatform("github")}><Icon name="github" s={12} /> GitHub</span>
        <span className={`chip ${platform === "gitlab" ? "is-active" : ""}`} onClick={() => setPlatform("gitlab")} style={{ color: "#FC6D26" }}>GitLab</span>
        <span className={`chip ${platform === "huggingface" ? "is-active" : ""}`} onClick={() => setPlatform("huggingface")}>🤗 HF</span>
        <span style={{ width: 1, alignSelf: "stretch", background: "var(--hairline)" }} />
        <span className={`chip ${healthFilter === "low" ? "is-active" : ""}`} onClick={() => setHealthFilter(healthFilter === "low" ? "all" : "low")}>health &lt; 70</span>
        <span className={`chip ${healthFilter === "high" ? "is-active" : ""}`} onClick={() => setHealthFilter(healthFilter === "high" ? "all" : "high")}>health ≥ 85</span>
        <span className="chip">findings &gt; 0</span>
        <span className="chip">+ Add filter</span>
        <span className="grow" />
        <span className="muted" style={{ fontSize: "var(--t-12)" }}>{filtered.length} matched</span>
      </div>

      <div className="card" style={{ overflow: "hidden", padding: 0 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 32 }}><input type="checkbox" /></th>
              <th>Repository</th>
              <th style={{ width: 100 }}>Platform</th>
              <th style={{ width: 100 }}>Lang</th>
              <th style={{ width: 130 }}>Health</th>
              <th style={{ width: 100 }}>Findings</th>
              <th style={{ width: 90 }}>Repairs</th>
              <th style={{ width: 110 }}>Last job</th>
              <th style={{ width: 120 }}>14d activity</th>
              <th style={{ width: 28 }}></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={r.id} className={r.id === "R-1045" ? "is-selected" : ""} onClick={() => onNav("repo", r.id)}>
                <td><input type="checkbox" onClick={(e) => e.stopPropagation()} /></td>
                <td>
                  <div className="row gap-2">
                    <RepoIcon platform={r.platform} s={13} />
                    <span style={{ fontWeight: 500 }}>{r.name}</span>
                    {r.visibility === "private" && <span className="pill" style={{ height: 18, padding: "0 6px", fontSize: 10.5 }}>private</span>}
                  </div>
                </td>
                <td className="muted" style={{ textTransform: "capitalize" }}>{r.platform}</td>
                <td className="muted">{r.lang}</td>
                <td><HealthBar value={r.health} /></td>
                <td>
                  {r.openFindings > 0 ? (
                    <span className="row gap-2">
                      <SeverityDot level={r.openFindings > 10 ? "critical" : r.openFindings > 5 ? "high" : "medium"} />
                      <span className="mono">{r.openFindings}</span>
                    </span>
                  ) : (
                    <span className="faint mono">—</span>
                  )}
                </td>
                <td className="mono muted">{r.repairs}</td>
                <td className="muted" style={{ fontSize: "var(--t-12)" }}>{r.lastJob}</td>
                <td><Sparkline data={D.spark(i + 2)} w={96} h={20} stroke="var(--cyan)" /></td>
                <td><Icon name="more" s={14} style={{ color: "var(--fg-faint)" }} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row" style={{ marginTop: 10, justifyContent: "space-between", fontSize: "var(--t-12)", color: "var(--fg-muted)" }}>
        <span>Showing 1–{filtered.length} of 1,284</span>
        <div className="row gap-2">
          <button className="btn btn-sm" disabled style={{ opacity: 0.5 }}>← Prev</button>
          {[1, 2, 3, "…", 75].map((p, i) => (
            <button key={i} className={`btn btn-sm ${p === 1 ? "btn-primary" : ""}`}>{p}</button>
          ))}
          <button className="btn btn-sm">Next →</button>
        </div>
      </div>
    </div>
  );
};
