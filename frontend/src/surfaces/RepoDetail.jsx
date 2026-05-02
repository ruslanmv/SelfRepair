import React from "react";

import { Icon, Pill, RepoIcon, SeverityDot, StateBadge } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const RepoDetail = ({ repoId, onNav, onOpenAudit, onOpenRun }) => {
  const repo = D.repos.find((r) => r.id === repoId) || D.repos[3];
  const [tab, setTab] = React.useState("overview");
  const findings = D.findings.filter((f) => f.repo === repo.name);
  const repairs = D.repairs.filter((r) => r.repo === repo.name);
  const jobs = D.jobs.filter((j) => j.repo === repo.name);

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div className="col gap-1">
          <div className="row gap-2 muted" style={{ fontSize: "var(--t-12)" }}>
            <RepoIcon platform={repo.platform} s={12} />
            <span>{repo.platform}</span>
            <span>·</span>
            <span>{repo.owner}</span>
          </div>
          <div className="row gap-3" style={{ alignItems: "center" }}>
            <h1 style={{ margin: 0, fontSize: "var(--t-24)", letterSpacing: "-0.01em", fontWeight: 600 }}>{repo.name.split("/")[1]}</h1>
            <Pill>{repo.visibility}</Pill>
            <Pill tone="info"><Icon name="branch" s={11} /> {repo.branch}</Pill>
            <span className="sha mono">a8f12c4</span>
          </div>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: "var(--t-13)" }}>
            SelfRepair Repo · open-source AI Secure Delivery Copilot · {repo.lang} · {repo.stars > 0 ? `★ ${repo.stars}` : "internal"}
          </p>
        </div>
        <div className="row gap-2">
          <button className="btn"><Icon name="external" s={13} /> Open on {repo.platform}</button>
          <button className="btn" onClick={() => onOpenAudit?.("repo", repo.id)}><Icon name="audit" s={13} /> Audit</button>
          <button className="btn"><Icon name="retry" s={13} /> Re-scan</button>
          <button className="btn btn-primary" onClick={() => onOpenRun?.(repo.name)}><Icon name="play" s={12} /> Run repair</button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, marginBottom: 12, display: "grid", gridTemplateColumns: "repeat(5, 1fr)" }}>
        {[
          { l: "Health score", v: repo.health, sub: repo.health >= 85 ? "excellent" : repo.health >= 65 ? "fair" : "needs work", tone: repo.health >= 85 ? "ok" : repo.health >= 65 ? "warn" : "danger" },
          { l: "Open findings", v: repo.openFindings, sub: "3 high · 2 med · 1 low", tone: "warn" },
          { l: "Repairs (30d)", v: repo.repairs, sub: "92% merged", tone: "ok" },
          { l: "Last scan", v: repo.lastJob, sub: "via webhook:push", tone: "info" },
          { l: "Coverage", v: "82%", sub: "+4% this week", tone: "ok" },
        ].map((s, i) => (
          <div key={i} style={{ padding: "14px 16px", borderRight: i < 4 ? "1px solid var(--hairline)" : "none" }}>
            <div className="muted" style={{ fontSize: "var(--t-12)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>{s.l}</div>
            <div style={{ fontSize: "var(--t-24)", fontWeight: 600, letterSpacing: "-0.01em" }}>{s.v}</div>
            <div className="muted" style={{ fontSize: "var(--t-12)", color: `var(--${s.tone})`, opacity: 0.85 }}>{s.sub}</div>
          </div>
        ))}
      </div>

      <div className="tabs" style={{ marginBottom: 12 }}>
        {[
          { id: "overview", label: "Overview" },
          { id: "checks", label: "Checks", count: 14 },
          { id: "findings", label: "Findings", count: findings.length },
          { id: "repairs", label: "Repairs", count: repairs.length },
          { id: "jobs", label: "Jobs", count: jobs.length },
          { id: "config", label: ".selfrepair.yml" },
        ].map((t) => (
          <span key={t.id} className={`tab ${tab === t.id ? "is-active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}{t.count != null && <span className="tab-count">{t.count}</span>}
          </span>
        ))}
      </div>

      {tab === "overview" && (
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 12 }}>
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section"><h2>Standards & checks</h2><span className="faint" style={{ fontSize: "var(--t-12)" }}>14 of 16 passing</span></div>
            <div className="col" style={{ marginTop: 8 }}>
              {[
                { name: "Makefile · install / test / start", state: "ok", detail: "all targets present" },
                { name: "pyproject.toml", state: "warn", detail: "missing [tool.uv] section · auto-fixable" },
                { name: "Python ≥ 3.11", state: "ok", detail: "requires-python = '>=3.11'" },
                { name: "tests/test_health.py", state: "ok", detail: "1 test · last run 4m ago" },
                { name: "README front-matter (HF)", state: "ok", detail: "valid" },
                { name: "License (Apache-2.0)", state: "ok", detail: "detected" },
                { name: "Secrets scan", state: "ok", detail: "0 findings" },
                { name: "SBOM", state: "warn", detail: "not generated · suggest auto-fix" },
              ].map((c, i) => (
                <div key={i} className="row gap-3" style={{ padding: "8px 4px", borderBottom: "1px solid var(--hairline)" }}>
                  <span style={{ width: 16, display: "inline-flex", color: c.state === "ok" ? "var(--ok)" : "var(--warn)" }}>
                    <Icon name={c.state === "ok" ? "check" : "findings"} s={14} />
                  </span>
                  <span style={{ flex: 1, fontSize: "var(--t-13)" }}>{c.name}</span>
                  <span className="muted" style={{ fontSize: "var(--t-12)" }}>{c.detail}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div className="h-section"><h2>Recent jobs</h2></div>
            <div className="col" style={{ marginTop: 4 }}>
              {jobs.concat(D.jobs.slice(0, 4)).slice(0, 5).map((j, i) => (
                <div key={i} className="row gap-3" style={{ padding: "8px 0", borderBottom: "1px solid var(--hairline)", cursor: "pointer" }} onClick={() => onNav("job", j.id)}>
                  <StateBadge state={j.state} />
                  <div className="col grow" style={{ minWidth: 0 }}>
                    <span className="mono" style={{ fontSize: "var(--t-13)" }}>{j.id}</span>
                    <span className="faint" style={{ fontSize: "var(--t-12)" }}>{j.trigger} · {j.events} events</span>
                  </div>
                  <span className="mono muted" style={{ fontSize: "var(--t-12)" }}>{j.duration}</span>
                </div>
              ))}
            </div>
            <div className="h-section" style={{ marginTop: 16 }}><h2>Top findings</h2></div>
            {findings.slice(0, 4).map((f, i) => (
              <div key={i} className="row gap-3" style={{ padding: "8px 0", borderBottom: "1px solid var(--hairline)", cursor: "pointer" }}>
                <SeverityDot level={f.severity} />
                <span className="mono" style={{ flex: 1, fontSize: "var(--t-13)" }}>{f.kind}</span>
                <span className="faint mono" style={{ fontSize: "var(--t-12)" }}>×{f.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "config" && (
        <div className="card" style={{ padding: 0 }}>
          <div className="row" style={{ padding: "10px 14px", borderBottom: "1px solid var(--hairline)", justifyContent: "space-between" }}>
            <div className="row gap-2">
              <span className="mono" style={{ fontSize: "var(--t-13)" }}>.selfrepair.yml</span>
              <Pill tone="ok" dot>valid</Pill>
            </div>
            <div className="row gap-2">
              <button className="btn btn-sm">Schema docs</button>
              <button className="btn btn-sm btn-primary">Save</button>
            </div>
          </div>
          <pre className="code" style={{ margin: 0, borderRadius: 0, border: "none", padding: "14px 16px", lineHeight: 1.65 }}>{`# .selfrepair.yml — repository policy
version: 1
profile: enterprise

discovery:
  branches: [main, master]
  include_drafts: false

analyzers:
  - layout
  - standards
  - health-tests
  - secrets
  - sbom

heal:
  strategies:
    - auto-fix:pyproject
    - auto-fix:makefile
    - auto-fix:health_test
    - llm-assist          # OllaBridge-powered
  max_attempts: 3

policy:
  deny_paths:
    - "secrets/**"
    - ".env*"
  require_human_approval:
    - llm-assist
    - schema-changes
  budget:
    repair_tokens: 200_000`}</pre>
        </div>
      )}

      {tab !== "overview" && tab !== "config" && (
        <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--fg-muted)" }}>
          <span className="faint">{tab} tab content</span>
        </div>
      )}
    </div>
  );
};
