import React from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/StateScreens.jsx";
import { useAdminAudit } from "../../hooks/useAdmin.js";

const PAGE_SIZE = 50;

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

export function AdminLogs() {
  const [actionInput, setActionInput] = React.useState("");
  const [actorInput, setActorInput] = React.useState("");
  const [filters, setFilters] = React.useState({ query: "", actor: "" });
  const [offset, setOffset] = React.useState(0);

  const params = {
    query: filters.query || undefined,
    actor: filters.actor || undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const audit = useAdminAudit(params);

  const submit = (e) => {
    e.preventDefault();
    setOffset(0);
    setFilters({ query: actionInput.trim(), actor: actorInput.trim() });
  };

  const items = audit.data?.items || [];
  const count = audit.data?.count || 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
          Admin logs
        </h1>
        <p
          className="muted"
          style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
        >
          The complete audit trail across all users, filterable by action and
          actor.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="card"
        style={{ padding: 12, marginBottom: 12, display: "flex", gap: 8 }}
      >
        <input
          className="input"
          placeholder="action contains… (e.g. admin_)"
          value={actionInput}
          onChange={(e) => setActionInput(e.target.value)}
          style={{ flex: 1 }}
        />
        <input
          className="input"
          placeholder="actor user id"
          value={actorInput}
          onChange={(e) => setActorInput(e.target.value)}
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" type="submit">
          Filter
        </button>
      </form>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {audit.isLoading && !audit.data && <LoadingState label="Loading audit…" />}
        {audit.isError && (
          <ErrorState
            title="Could not load the audit trail"
            message={audit.error?.detail || "Please retry."}
            onRetry={() => audit.refetch()}
          />
        )}
        {!audit.isLoading && !audit.isError && items.length === 0 && (
          <EmptyState
            title="No audit rows"
            message="No entries match these filters."
          />
        )}
        {items.length > 0 && (
          <div className="scroll-x-mobile" style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 90 }}>ID</th>
                  <th style={{ width: 220 }}>Actor</th>
                  <th style={{ width: 200 }}>Action</th>
                  <th>Details</th>
                  <th style={{ width: 200 }}>When</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td className="mono">{r.id}</td>
                    <td className="mono muted">{r.actor}</td>
                    <td className="mono">{r.action}</td>
                    <td className="muted">{r.details}</td>
                    <td className="muted">{fmtDate(r.ts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div
        className="row"
        style={{ justifyContent: "space-between", marginTop: 12 }}
      >
        <span className="muted" style={{ fontSize: 12 }}>
          {count} entr{count === 1 ? "y" : "ies"} · page {page} of {pages}
        </span>
        <div className="row gap-2">
          <button
            className="btn"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            className="btn"
            disabled={offset + PAGE_SIZE >= count}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
