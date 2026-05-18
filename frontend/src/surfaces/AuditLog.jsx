import React from "react";

import { auditExportUrl } from "../api/audit.js";
import { useAudit } from "../hooks/useAudit.js";

export function AuditLog() {
  const [actor, setActor] = React.useState("");
  const [action, setAction] = React.useState("");
  const [targetType, setTargetType] = React.useState("");
  const params = {
    actor: actor || undefined,
    action: action || undefined,
    target_type: targetType || undefined,
    limit: 100,
  };
  const audit = useAudit(params);

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
            Audit log
          </h1>
          <p
            className="muted"
            style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
          >
            Tamper-evident operator actions, scoped to the current org.
          </p>
        </div>
        <a
          className="btn"
          href={`/api${auditExportUrl(params)}`}
          target="_blank"
          rel="noreferrer"
        >
          Export NDJSON
        </a>
      </div>

      <div
        className="card"
        style={{ padding: 12, marginBottom: 12, display: "flex", gap: 8 }}
      >
        <input
          placeholder="actor"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          style={{ flex: 1, padding: "6px 8px" }}
        />
        <input
          placeholder="action"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          style={{ flex: 1, padding: "6px 8px" }}
        />
        <input
          placeholder="target type (job, repair, repo, finding)"
          value={targetType}
          onChange={(e) => setTargetType(e.target.value)}
          style={{ flex: 1.4, padding: "6px 8px" }}
        />
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {audit.isLoading && (
          <div className="muted" style={{ padding: 16 }}>
            Loading…
          </div>
        )}
        {audit.isError && (
          <div
            className="muted"
            style={{ padding: 16, color: "var(--danger)" }}
          >
            {audit.error?.detail || "Could not load audit log"}
          </div>
        )}
        {audit.data?.items?.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No audit rows match these filters.
          </div>
        )}
        {audit.data?.items?.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 80 }}>ID</th>
                <th style={{ width: 200 }}>Actor</th>
                <th style={{ width: 130 }}>Action</th>
                <th style={{ width: 110 }}>Target</th>
                <th>Target ID</th>
                <th style={{ width: 200 }}>When</th>
              </tr>
            </thead>
            <tbody>
              {audit.data.items.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id}</td>
                  <td>{r.actor}</td>
                  <td className="mono muted">{r.action}</td>
                  <td className="mono muted">{r.target_type}</td>
                  <td className="mono muted">{r.target_id}</td>
                  <td className="muted">{r.ts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
