import React from "react";

import { Pill, SeverityDot, StateBadge } from "../components/atoms.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/StateScreens.jsx";
import { useInbox, useInboxJob } from "../hooks/useInbox.js";

function formatWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const HealthScore = ({ value }) => {
  if (value == null) return <span className="muted">—</span>;
  const color =
    value >= 85 ? "var(--ok)" : value >= 65 ? "var(--warn)" : "var(--danger)";
  return (
    <span className="mono" style={{ color, fontWeight: 600 }}>
      {value}
    </span>
  );
};

const JobReport = ({ jobId }) => {
  const { data, isLoading, isError, error } = useInboxJob(jobId);
  if (isLoading) {
    return <div className="muted" style={{ padding: 16 }}>Loading report…</div>;
  }
  if (isError) {
    return (
      <div className="muted" style={{ padding: 16, color: "var(--danger)" }}>
        {error?.detail || "Could not load report"}
      </div>
    );
  }
  const report = data?.report;
  if (!report) {
    return (
      <div className="muted" style={{ padding: 16 }}>
        {data?.error || "No report available yet."}
      </div>
    );
  }
  const issues = report.issues || [];
  return (
    <div style={{ padding: 16 }}>
      <div className="row gap-2" style={{ marginBottom: 12, flexWrap: "wrap" }}>
        <Pill tone="neutral">{report.source || "github-api"}</Pill>
        <Pill tone="info">Health {report.health_score ?? "—"}</Pill>
        <Pill tone="neutral">{report.file_count ?? 0} files</Pill>
        {report.note && <Pill tone="warn">{report.note}</Pill>}
      </div>
      {issues.length === 0 ? (
        <div className="muted" style={{ fontSize: "var(--t-13)" }}>
          No issues detected.
        </div>
      ) : (
        <div className="scroll-x-mobile">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 50 }}>Sev</th>
                <th style={{ width: 180 }}>Detector</th>
                <th>Description</th>
                <th>Recommended action</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((iss) => (
                <tr key={iss.id}>
                  <td><SeverityDot level={iss.severity} /></td>
                  <td className="mono muted">{iss.id}</td>
                  <td>{iss.description}</td>
                  <td className="muted">{iss.recommended_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export const Inbox = () => {
  const { data, isLoading, isError, error, refetch } = useInbox();
  const [expanded, setExpanded] = React.useState(null);
  const items = data?.items || [];

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>Inbox</h1>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
            Incoming maintenance requests from clients · {data?.count || 0} total
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {isLoading && <LoadingState label="Loading inbox…" />}
        {isError && (
          <ErrorState
            code="MOB-INBOX-001"
            title="Unable to load the inbox"
            message={error?.detail || "Could not load incoming requests."}
            onRetry={() => refetch()}
          />
        )}
        {!isLoading && !isError && items.length === 0 && (
          <EmptyState
            title="No requests yet"
            message="When a client submits a maintenance plan, it will appear here with its health-check result."
          />
        )}
        {items.length > 0 && (
          <div className="scroll-x-mobile">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 180 }}>Requested by</th>
                  <th>Repo</th>
                  <th style={{ width: 100 }}>Mode</th>
                  <th style={{ width: 120 }}>Status</th>
                  <th style={{ width: 80 }}>Health</th>
                  <th style={{ width: 150 }}>When</th>
                </tr>
              </thead>
              <tbody>
                {items.map((m) => {
                  const finished = m.status === "done" || m.status === "failed";
                  const isOpen = expanded === m.id;
                  return (
                    <React.Fragment key={m.id}>
                      <tr
                        onClick={() =>
                          finished && m.job_id
                            ? setExpanded(isOpen ? null : m.id)
                            : undefined
                        }
                        style={{ cursor: finished && m.job_id ? "pointer" : "default" }}
                      >
                        <td>
                          <div className="col" style={{ minWidth: 0 }}>
                            <span className="truncate">{m.client_id}</span>
                            {m.requested_by && (
                              <span className="faint" style={{ fontSize: 11 }}>
                                {m.requested_by}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="muted truncate">{m.repo_url}</td>
                        <td><Pill tone="neutral">{m.mode}</Pill></td>
                        <td><StateBadge state={m.status} /></td>
                        <td><HealthScore value={m.health_score} /></td>
                        <td className="muted" style={{ fontSize: "var(--t-12)" }}>
                          {formatWhen(m.created_at)}
                        </td>
                      </tr>
                      {isOpen && m.job_id && (
                        <tr>
                          <td colSpan={6} style={{ padding: 0, background: "var(--bg-elev-2)" }}>
                            <JobReport jobId={m.job_id} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
