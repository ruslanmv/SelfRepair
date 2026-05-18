import React from "react";

import {
  Icon,
  SeverityDot,
  StateBadge,
} from "../components/atoms.jsx";
import { useFindings } from "../hooks/useFindings.js";

const SEVERITIES = ["critical", "high", "medium", "low"];

export const Findings = () => {
  const [severity, setSeverity] = React.useState(undefined);
  const [statusFilter, setStatusFilter] = React.useState(undefined);
  const [q, setQ] = React.useState("");
  const params = {
    severity,
    status: statusFilter,
    q: q || undefined,
    limit: 100,
  };
  const { data, isLoading, isError, error } = useFindings(params);
  const items = data?.items || [];

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", marginBottom: 12 }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
            Findings
          </h1>
          <p
            className="muted"
            style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
          >
            Fleet-wide, grouped by fingerprint
          </p>
        </div>
        <div className="row gap-2">
          <button className="btn" disabled>Bulk suppress…</button>
          <button className="btn btn-primary" disabled>
            Open triage queue
          </button>
        </div>
      </div>
      <div
        className="row gap-2"
        style={{ marginBottom: 10, flexWrap: "wrap" }}
      >
        <span
          className={`chip ${!severity ? "is-active" : ""}`}
          onClick={() => setSeverity(undefined)}
        >
          all
        </span>
        {SEVERITIES.map((s) => (
          <span
            key={s}
            className={`chip ${severity === s ? "is-active" : ""}`}
            onClick={() => setSeverity(severity === s ? undefined : s)}
          >
            {s}
          </span>
        ))}
        <span style={{ width: 1, alignSelf: "stretch", background: "var(--hairline)" }} />
        {["open", "fixed", "suppressed"].map((st) => (
          <span
            key={st}
            className={`chip ${statusFilter === st ? "is-active" : ""}`}
            onClick={() => setStatusFilter(statusFilter === st ? undefined : st)}
          >
            {st}
          </span>
        ))}
        <span className="grow" />
        <input
          className="input"
          placeholder="Search kind, fingerprint, CWE…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ width: 260 }}
        />
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
            {error?.detail || "Could not load findings"}
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No findings match these filters.
          </div>
        )}
        {items.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 28 }}>Sev</th>
                <th>Fingerprint · kind</th>
                <th style={{ width: 220 }}>Repo</th>
                <th style={{ width: 140 }}>Last seen</th>
                <th style={{ width: 130 }}>State</th>
                <th style={{ width: 100 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((f) => (
                <tr key={f.id}>
                  <td><SeverityDot level={f.severity} /></td>
                  <td>
                    <div className="col">
                      <span
                        className="mono"
                        style={{ fontSize: "var(--t-13)" }}
                      >
                        {f.kind}
                      </span>
                      <span
                        className="faint mono"
                        style={{ fontSize: "var(--t-12)" }}
                      >
                        {f.fingerprint?.slice(0, 16)}
                        {f.cwe ? ` · ${f.cwe}` : ""}
                        {f.cve ? ` · ${f.cve}` : ""}
                      </span>
                    </div>
                  </td>
                  <td className="muted mono">{f.repo_id?.slice(0, 8)}</td>
                  <td
                    className="muted"
                    style={{ fontSize: "var(--t-12)" }}
                    title={f.last_seen_at}
                  >
                    {f.last_seen_at
                      ? new Date(f.last_seen_at).toLocaleString()
                      : "—"}
                  </td>
                  <td><StateBadge state={f.status} /></td>
                  <td>
                    <button className="btn btn-sm" disabled>
                      <Icon name="caret" s={11} /> Triage
                    </button>
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
