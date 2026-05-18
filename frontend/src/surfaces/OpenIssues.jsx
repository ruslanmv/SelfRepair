import React from "react";

import {
  Icon,
  Pill,
  RepoIcon,
  SeverityDot,
  StateBadge,
} from "../components/atoms.jsx";
import {
  useIssues,
  useRunRepairFromIssue,
  useSyncIssues,
} from "../hooks/useIssues.js";

const PROVIDERS = [
  { id: undefined, label: "All" },
  { id: "github", label: "GitHub" },
  { id: "gitlab", label: "GitLab" },
  { id: "huggingface", label: "Hugging Face" },
];

const PRIORITIES = [
  { id: undefined, label: "All priorities" },
  { id: "critical", label: "critical" },
  { id: "high", label: "high" },
  { id: "medium", label: "medium" },
  { id: "low", label: "low" },
];

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

function normaliseState(s) {
  return s === "opened" ? "open" : s;
}

function sevForPriority(p) {
  if (p === "critical") return "critical";
  if (p === "high") return "high";
  if (p === "medium") return "medium";
  return "low";
}

const KpiCard = ({ label, value, hint, tone = "info" }) => (
  <div className="card" style={{ padding: 14, minWidth: 180 }}>
    <div
      className="muted"
      style={{ fontSize: "var(--t-12)", letterSpacing: "0.02em" }}
    >
      {label}
    </div>
    <div
      className="row"
      style={{ alignItems: "baseline", gap: 8, marginTop: 4 }}
    >
      <span style={{ fontSize: "var(--t-22)", fontWeight: 600 }}>{value}</span>
      {hint && (
        <span
          className={`pill pill-${tone}`}
          style={{ height: 18, fontSize: 10.5 }}
        >
          {hint}
        </span>
      )}
    </div>
  </div>
);

export const OpenIssues = ({ onOpenRun }) => {
  const [q, setQ] = React.useState("");
  const [provider, setProvider] = React.useState(undefined);
  const [priority, setPriority] = React.useState(undefined);
  const [onlyRepairable, setOnlyRepairable] = React.useState(false);
  const params = {
    provider,
    priority,
    repairable: onlyRepairable ? true : undefined,
    limit: 200,
  };
  const { data, isLoading, isError, error } = useIssues(params);
  const sync = useSyncIssues();
  const runRepair = useRunRepairFromIssue();

  const items = (data?.items || []).filter((i) => {
    if (!q) return true;
    const lq = q.toLowerCase();
    const labels = (i.labels || []).join(" ");
    const haystack = `${i.title} ${i.author || ""} ${labels}`.toLowerCase();
    return haystack.includes(lq);
  });

  const kpis = {
    open: items.filter((i) => normaliseState(i.state) === "open").length,
    high: items.filter((i) =>
      ["high", "critical"].includes(i.priority),
    ).length,
    repairable: items.filter((i) => i.repairable).length,
  };

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", marginBottom: 12 }}
      >
        <div>
          <h1
            style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}
          >
            Open Issues
          </h1>
          <p
            className="muted"
            style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
          >
            Human-created GitHub, GitLab, and Hugging Face issues.
          </p>
        </div>
        <div className="row gap-2">
          <button
            className="btn"
            onClick={() => sync.mutate({})}
            disabled={sync.isPending}
            title="Re-sync external issue providers"
          >
            <Icon name="repos" s={13} />
            {sync.isPending ? " Syncing…" : " Sync now"}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => onOpenRun && onOpenRun(null)}
          >
            <Icon name="play" s={12} /> Run repair from issue
          </button>
        </div>
      </div>

      <div
        className="row gap-2"
        style={{ marginBottom: 12, flexWrap: "wrap" }}
      >
        <KpiCard label="Open issues" value={kpis.open} tone="info" />
        <KpiCard
          label="High priority"
          value={kpis.high}
          hint="needs attention"
          tone="warn"
        />
        <KpiCard
          label="Repairable"
          value={kpis.repairable}
          hint="auto-fix candidates"
          tone="ok"
        />
      </div>

      <div
        className="row gap-2"
        style={{ marginBottom: 10, flexWrap: "wrap" }}
      >
        <div style={{ position: "relative" }}>
          <Icon
            name="search"
            s={13}
            style={{
              position: "absolute",
              left: 9,
              top: 8,
              color: "var(--fg-faint)",
            }}
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
            key={p.label}
            className={`chip ${provider === p.id ? "is-active" : ""}`}
            onClick={() => setProvider(p.id)}
          >
            {p.label}
          </span>
        ))}
        <span
          style={{
            width: 1,
            alignSelf: "stretch",
            background: "var(--hairline)",
          }}
        />
        {PRIORITIES.map((p) => (
          <span
            key={p.label}
            className={`chip ${priority === p.id ? "is-active" : ""}`}
            onClick={() => setPriority(p.id)}
          >
            {p.label}
          </span>
        ))}
        <span
          className={`chip ${onlyRepairable ? "is-active" : ""}`}
          onClick={() => setOnlyRepairable((v) => !v)}
        >
          Repairable only
        </span>
        <span className="grow" />
        <span className="muted" style={{ fontSize: "var(--t-12)" }}>
          {items.length} matched
        </span>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {isLoading && (
          <div className="muted" style={{ padding: 16 }}>Loading…</div>
        )}
        {isError && (
          <div
            className="muted"
            style={{ padding: 16, color: "var(--danger)" }}
          >
            {error?.detail || "Could not load issues"}
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No issues match these filters.
          </div>
        )}
        {items.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 28 }}>Sev</th>
                <th>Issue</th>
                <th style={{ width: 110 }}>Provider</th>
                <th style={{ width: 140 }}>Class</th>
                <th style={{ width: 160 }}>Labels</th>
                <th style={{ width: 110 }}>Author</th>
                <th style={{ width: 110 }}>State</th>
                <th style={{ width: 130 }}>Updated</th>
                <th style={{ width: 240 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>
                    <SeverityDot level={sevForPriority(i.priority)} />
                  </td>
                  <td>
                    <div className="col">
                      <span style={{ fontWeight: 500 }}>
                        <span
                          className="faint mono"
                          style={{ marginRight: 6 }}
                        >
                          #{i.number}
                        </span>
                        {i.title}
                      </span>
                      {i.body_excerpt && (
                        <span
                          className="faint"
                          style={{ fontSize: "var(--t-12)", marginTop: 2 }}
                        >
                          {i.body_excerpt}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="row gap-2">
                      <RepoIcon platform={i.provider} s={13} />
                      <span className="muted" style={{ fontSize: "var(--t-12)" }}>
                        {i.provider}
                      </span>
                    </div>
                  </td>
                  <td>
                    <Pill tone={CLASS_TONE[i.repair_class] || "neutral"}>
                      {(i.repair_class || "unknown").replace(/_/g, " ")}
                    </Pill>
                  </td>
                  <td>
                    <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                      {(i.labels || []).slice(0, 2).map((l) => (
                        <span
                          key={l}
                          className="pill"
                          style={{ height: 18, fontSize: 10.5 }}
                        >
                          {l}
                        </span>
                      ))}
                      {(i.labels || []).length > 2 && (
                        <span
                          className="faint mono"
                          style={{ fontSize: 10.5 }}
                          title={(i.labels || []).slice(2).join(", ")}
                        >
                          +{i.labels.length - 2}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="muted" style={{ fontSize: "var(--t-12)" }}>
                    {i.author || "—"}
                  </td>
                  <td>
                    <StateBadge state={normaliseState(i.state)} />
                  </td>
                  <td className="muted" style={{ fontSize: "var(--t-12)" }}>
                    {i.updated_at_external
                      ? new Date(i.updated_at_external).toLocaleString()
                      : "—"}
                  </td>
                  <td>
                    <div className="row gap-2">
                      <a
                        className="btn btn-sm"
                        href={i.html_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Icon name="external" s={11} /> Open
                      </a>
                      {i.repairable ? (
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() =>
                            runRepair.mutate({ id: i.id, body: {} })
                          }
                          disabled={runRepair.isPending}
                        >
                          <Icon name="play" s={11} /> Run repair
                        </button>
                      ) : (
                        <button className="btn btn-sm" disabled>
                          <Icon name="shield" s={11} /> Triage
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
