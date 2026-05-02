import React from "react";

import { Icon, Pill, RepoIcon, SeverityDot, StateBadge } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

// Open Issues — human-created issues from GitHub, GitLab, and Hugging Face.
// Distinct from Findings (internal scanner output) and Repairs (internal jobs).
// Mirrors Findings/Repos in layout: KPI strip → filters → table → row actions.
// All actions are mock-only in the UI MVP; the backend `/v1/issues` surface
// lands in Batch 2 and 3.

const PROVIDERS = [
  { id: "all", label: "All" },
  { id: "github", label: "GitHub", icon: "github" },
  { id: "gitlab", label: "GitLab" },
  { id: "huggingface", label: "Hugging Face" },
];

const PRIORITY_LEVELS = ["all", "critical", "high", "medium", "low"];

// Map repair classes onto the same Pill tones the rest of the app uses so
// "repairable" classes line up visually with the green ones in Findings.
const CLASS_TONE = {
  documentation: "ok",
  dependency: "ok",
  configuration: "ok",
  ci_failure: "info",
  runtime: "info",
  bug: "warn",
  feature_request: "neutral",
  security: "danger",
  unknown: "neutral",
};

const formatClass = (cls) => cls.replace(/_/g, " ");

// "opened" is GitLab's vocabulary for what GitHub calls "open"; normalise so
// the StateBadge component (built around GitHub's open/closed) renders cleanly.
const normaliseState = (state) => (state === "opened" ? "open" : state);

const KpiCard = ({ label, value, hint, tone = "info" }) => (
  <div className="card" style={{ padding: 14, minWidth: 180 }}>
    <div className="muted" style={{ fontSize: "var(--t-12)", letterSpacing: "0.02em" }}>
      {label}
    </div>
    <div
      className="row"
      style={{ alignItems: "baseline", gap: 8, marginTop: 4 }}
    >
      <span style={{ fontSize: "var(--t-22)", fontWeight: 600 }}>{value}</span>
      {hint && (
        <span className={`pill pill-${tone}`} style={{ height: 18, fontSize: 10.5 }}>
          {hint}
        </span>
      )}
    </div>
  </div>
);

export const OpenIssues = ({ onOpenRun }) => {
  const [q, setQ] = React.useState("");
  const [provider, setProvider] = React.useState("all");
  const [priority, setPriority] = React.useState("all");
  const [onlyRepairable, setOnlyRepairable] = React.useState(false);

  const filtered = D.externalIssues.filter((i) => {
    if (q) {
      const lq = q.toLowerCase();
      const haystack = `${i.title} ${i.repo} ${i.author} ${i.labels.join(" ")}`.toLowerCase();
      if (!haystack.includes(lq)) return false;
    }
    if (provider !== "all" && i.provider !== provider) return false;
    if (priority !== "all" && i.priority !== priority) return false;
    if (onlyRepairable && !i.repairable) return false;
    return true;
  });

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", letterSpacing: "-0.01em", fontWeight: 600 }}>
            Open Issues
          </h1>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
            Human-created GitHub, GitLab, and Hugging Face issues across connected repos
          </p>
        </div>
        <div className="row gap-2">
          <button className="btn">
            <Icon name="filter" s={13} /> Saved views
          </button>
          <button className="btn">
            <Icon name="repos" s={13} /> Sync now
          </button>
          <button
            className="btn btn-primary"
            onClick={() => onOpenRun && onOpenRun(null)}
            title="Run repair from a selected issue"
          >
            <Icon name="play" s={12} /> Run repair from issue
          </button>
        </div>
      </div>

      <div
        className="row gap-2"
        style={{ marginBottom: 12, flexWrap: "wrap" }}
      >
        <KpiCard label="Open issues" value={D.issueKpis.open} hint="across 4 repos" tone="info" />
        <KpiCard
          label="High priority"
          value={D.issueKpis.highPriority}
          hint="needs attention"
          tone="warn"
        />
        <KpiCard
          label="Repairable"
          value={D.issueKpis.repairable}
          hint="auto-fix candidates"
          tone="ok"
        />
        <KpiCard
          label="Repairs started"
          value={D.issueKpis.repairsStarted}
          hint="from issues"
          tone="info"
        />
      </div>

      <div className="row gap-2" style={{ marginBottom: 10, flexWrap: "wrap" }}>
        <div style={{ position: "relative" }}>
          <Icon
            name="search"
            s={13}
            style={{ position: "absolute", left: 9, top: 8, color: "var(--fg-faint)" }}
          />
          <input
            className="input"
            placeholder="Search issues, labels, authors…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ paddingLeft: 28, width: 280 }}
          />
        </div>

        {PROVIDERS.map((p) => (
          <span
            key={p.id}
            className={`chip ${provider === p.id ? "is-active" : ""}`}
            onClick={() => setProvider(p.id)}
          >
            {p.id === "github" && <Icon name="github" s={12} />}
            {p.id === "gitlab" && <span style={{ color: "#FC6D26" }}>●</span>}
            {p.id === "huggingface" && <span>🤗</span>}
            {p.label}
          </span>
        ))}

        <span
          style={{ width: 1, alignSelf: "stretch", background: "var(--hairline)" }}
        />

        {PRIORITY_LEVELS.map((p) => (
          <span
            key={p}
            className={`chip ${priority === p ? "is-active" : ""}`}
            onClick={() => setPriority(p)}
            style={{ textTransform: "capitalize" }}
          >
            {p === "all" ? "All priorities" : p}
          </span>
        ))}

        <span
          className={`chip ${onlyRepairable ? "is-active" : ""}`}
          onClick={() => setOnlyRepairable((v) => !v)}
        >
          ✓ Repairable only
        </span>

        <span className="grow" />
        <span className="muted" style={{ fontSize: "var(--t-12)" }}>
          {filtered.length} matched
        </span>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 32 }}>
                <input type="checkbox" />
              </th>
              <th style={{ width: 32 }}>Sev</th>
              <th>Issue</th>
              <th style={{ width: 200 }}>Repo</th>
              <th style={{ width: 140 }}>Class</th>
              <th style={{ width: 160 }}>Labels</th>
              <th style={{ width: 110 }}>Author</th>
              <th style={{ width: 110 }}>State</th>
              <th style={{ width: 100 }}>Updated</th>
              <th style={{ width: 130 }}>Linked</th>
              <th style={{ width: 240 }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((i) => (
              <tr key={i.id}>
                <td>
                  <input type="checkbox" onClick={(e) => e.stopPropagation()} />
                </td>
                <td>
                  <SeverityDot
                    level={
                      i.priority === "critical"
                        ? "critical"
                        : i.priority === "high"
                        ? "high"
                        : i.priority === "medium"
                        ? "medium"
                        : "low"
                    }
                  />
                </td>
                <td>
                  <div className="col">
                    <span style={{ fontWeight: 500 }}>
                      <span className="faint mono" style={{ marginRight: 6 }}>
                        #{i.number}
                      </span>
                      {i.title}
                    </span>
                    <span
                      className="faint"
                      style={{ fontSize: "var(--t-12)", marginTop: 2 }}
                    >
                      {i.bodyExcerpt}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="row gap-2">
                    <RepoIcon platform={i.provider} s={13} />
                    <span className="muted" style={{ fontSize: "var(--t-13)" }}>
                      {i.repo}
                    </span>
                  </div>
                </td>
                <td>
                  <Pill tone={CLASS_TONE[i.repairClass] || "neutral"}>
                    {formatClass(i.repairClass)}
                  </Pill>
                </td>
                <td>
                  <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                    {i.labels.slice(0, 2).map((l) => (
                      <span
                        key={l}
                        className="pill"
                        style={{ height: 18, fontSize: 10.5 }}
                      >
                        {l}
                      </span>
                    ))}
                    {i.labels.length > 2 && (
                      <span
                        className="faint mono"
                        style={{ fontSize: 10.5 }}
                        title={i.labels.slice(2).join(", ")}
                      >
                        +{i.labels.length - 2}
                      </span>
                    )}
                  </div>
                </td>
                <td className="muted" style={{ fontSize: "var(--t-12)" }}>
                  {i.author}
                </td>
                <td>
                  <StateBadge state={normaliseState(i.state)} />
                </td>
                <td className="muted" style={{ fontSize: "var(--t-12)" }}>
                  {i.updated}
                </td>
                <td>
                  {i.repairJobId ? (
                    <span
                      className="mono"
                      style={{ fontSize: "var(--t-12)", color: "var(--brand)" }}
                    >
                      {i.repairJobId}
                    </span>
                  ) : (
                    <span className="faint mono" style={{ fontSize: "var(--t-12)" }}>
                      —
                    </span>
                  )}
                </td>
                <td>
                  <div className="row gap-2">
                    <a
                      className="btn btn-sm"
                      href={i.externalUrl}
                      target="_blank"
                      rel="noreferrer"
                      title="Open on provider"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Icon name="external" s={11} /> Open
                    </a>
                    {i.repairable ? (
                      <button
                        className="btn btn-sm btn-primary"
                        title="Run a SelfRepair job from this issue"
                        onClick={() => onOpenRun && onOpenRun(i.repo)}
                      >
                        <Icon name="play" s={11} /> Run repair
                      </button>
                    ) : (
                      <button
                        className="btn btn-sm"
                        title={
                          i.repairClass === "security"
                            ? "Security issues are escalation-only"
                            : "Manual triage required"
                        }
                        disabled
                      >
                        <Icon name="shield" s={11} /> Triage
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        className="row"
        style={{
          marginTop: 10,
          justifyContent: "space-between",
          fontSize: "var(--t-12)",
          color: "var(--fg-muted)",
        }}
      >
        <span>
          Showing {filtered.length} of {D.externalIssues.length} synced ·
          last sync 2m ago
        </span>
        <div className="row gap-2">
          <span className="muted">Source:</span>
          <span className="chip">
            <Icon name="github" s={11} /> GitHub Issues
          </span>
          <span className="chip" style={{ color: "#FC6D26" }}>
            ● GitLab Issues
          </span>
          <span className="chip">🤗 HF Discussions</span>
        </div>
      </div>
    </div>
  );
};
