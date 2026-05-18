import React from "react";

import {
  HealthBar,
  Icon,
  RepoIcon,
  SeverityDot,
} from "../components/atoms.jsx";
import { useRepos } from "../hooks/useRepos.js";

function sevLevelForCount(n) {
  if (n === 0) return null;
  if (n > 10) return "critical";
  if (n > 5) return "high";
  return "medium";
}

export const Repos = ({ onNav }) => {
  const [q, setQ] = React.useState("");
  const [provider, setProvider] = React.useState("all");
  const [healthFilter, setHealthFilter] = React.useState("all");
  const [cursor, setCursor] = React.useState(undefined);

  const params = {
    q: q || undefined,
    provider: provider !== "all" ? provider : undefined,
    limit: 50,
    cursor,
  };
  const { data, isLoading, isError, error } = useRepos(params);
  const items = (data?.items || []).filter((r) => {
    if (healthFilter === "low" && r.health_score >= 70) return false;
    if (healthFilter === "high" && r.health_score < 85) return false;
    return true;
  });

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", marginBottom: 12 }}
      >
        <div>
          <h1
            style={{
              margin: 0,
              fontSize: "var(--t-24)",
              letterSpacing: "-0.01em",
              fontWeight: 600,
            }}
          >
            Repos
          </h1>
          <p
            className="muted"
            style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
          >
            {data?.count || 0} loaded · server-paginated
          </p>
        </div>
        <div className="row gap-2">
          <button className="btn">
            <Icon name="filter" s={13} /> Saved views
          </button>
          <button className="btn btn-primary">
            <Icon name="plus" s={13} /> Connect repo
          </button>
        </div>
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
            placeholder="Search repos…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setCursor(undefined);
            }}
            style={{ paddingLeft: 28, width: 240 }}
          />
        </div>
        <span
          className={`chip ${provider === "all" ? "is-active" : ""}`}
          onClick={() => {
            setProvider("all");
            setCursor(undefined);
          }}
        >
          All providers
        </span>
        <span
          className={`chip ${provider === "github" ? "is-active" : ""}`}
          onClick={() => {
            setProvider("github");
            setCursor(undefined);
          }}
        >
          <Icon name="github" s={12} /> GitHub
        </span>
        <span
          className={`chip ${provider === "gitlab" ? "is-active" : ""}`}
          onClick={() => {
            setProvider("gitlab");
            setCursor(undefined);
          }}
          style={{ color: "#FC6D26" }}
        >
          GitLab
        </span>
        <span
          className={`chip ${provider === "huggingface" ? "is-active" : ""}`}
          onClick={() => {
            setProvider("huggingface");
            setCursor(undefined);
          }}
        >
          HF
        </span>
        <span
          style={{
            width: 1,
            alignSelf: "stretch",
            background: "var(--hairline)",
          }}
        />
        <span
          className={`chip ${healthFilter === "low" ? "is-active" : ""}`}
          onClick={() =>
            setHealthFilter(healthFilter === "low" ? "all" : "low")
          }
        >
          health &lt; 70
        </span>
        <span
          className={`chip ${healthFilter === "high" ? "is-active" : ""}`}
          onClick={() =>
            setHealthFilter(healthFilter === "high" ? "all" : "high")
          }
        >
          health ≥ 85
        </span>
        <span className="grow" />
        <span
          className="muted"
          style={{ fontSize: "var(--t-12)" }}
        >
          {items.length} matched
        </span>
      </div>

      <div className="card" style={{ overflow: "hidden", padding: 0 }}>
        {isLoading && (
          <div className="muted" style={{ padding: 16 }}>Loading…</div>
        )}
        {isError && (
          <div
            className="muted"
            style={{ padding: 16, color: "var(--danger)" }}
          >
            {error?.detail || "Could not load repos"}
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>No repos found.</div>
        )}
        {items.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 32 }}><input type="checkbox" /></th>
                <th>Repository</th>
                <th style={{ width: 110 }}>Provider</th>
                <th style={{ width: 130 }}>Health</th>
                <th style={{ width: 100 }}>Findings</th>
                <th style={{ width: 90 }}>Repairs</th>
                <th style={{ width: 200 }}>Last job</th>
                <th style={{ width: 28 }}></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => {
                const sev = sevLevelForCount(r.open_findings);
                return (
                  <tr key={r.id} onClick={() => onNav("repo", r.id)}>
                    <td>
                      <input
                        type="checkbox"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td>
                      <div className="row gap-2">
                        <RepoIcon platform={r.provider} s={13} />
                        <span style={{ fontWeight: 500 }}>{r.full_name}</span>
                      </div>
                    </td>
                    <td className="muted" style={{ textTransform: "capitalize" }}>
                      {r.provider}
                    </td>
                    <td><HealthBar value={r.health_score} /></td>
                    <td>
                      {r.open_findings > 0 ? (
                        <span className="row gap-2">
                          <SeverityDot level={sev || "low"} />
                          <span className="mono">{r.open_findings}</span>
                        </span>
                      ) : (
                        <span className="faint mono">—</span>
                      )}
                    </td>
                    <td className="mono muted">{r.repair_count}</td>
                    <td
                      className="muted"
                      style={{ fontSize: "var(--t-12)" }}
                      title={r.last_job_at || ""}
                    >
                      {r.last_job_at
                        ? new Date(r.last_job_at).toLocaleString()
                        : "—"}
                    </td>
                    <td>
                      <Icon
                        name="more"
                        s={14}
                        style={{ color: "var(--fg-faint)" }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
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
          {data?.count || 0} loaded
          {data?.next_cursor ? " — more available" : ""}
        </span>
        <div className="row gap-2">
          <button
            className="btn btn-sm"
            disabled={!cursor}
            onClick={() => setCursor(undefined)}
          >
            ← First page
          </button>
          <button
            className="btn btn-sm"
            disabled={!data?.next_cursor}
            onClick={() => setCursor(data?.next_cursor)}
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
};
