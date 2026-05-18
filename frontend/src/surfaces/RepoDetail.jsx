import React from "react";

import {
  HealthBar,
  Icon,
  Pill,
  RepoIcon,
  SeverityDot,
  StateBadge,
} from "../components/atoms.jsx";
import { useFindings } from "../hooks/useFindings.js";
import { useJobs } from "../hooks/useJobs.js";
import { useRepoSummary, useSyncRepos } from "../hooks/useRepos.js";

function extractRepoName(fullName) {
  if (!fullName) return "";
  const parts = fullName.split("/");
  return parts[parts.length - 1] || fullName;
}

export const RepoDetail = ({ repoId, onNav, onOpenAudit, onOpenRun }) => {
  const summary = useRepoSummary(repoId);
  const findings = useFindings({
    repo_id: repoId,
    status: "open",
    limit: 50,
  });
  const jobs = useJobs({ repo_id: repoId, limit: 10 });
  const syncRepos = useSyncRepos();
  const [tab, setTab] = React.useState("overview");

  const repo = summary.data?.repo || summary.data || {};
  const repoFields = summary.data
    ? {
        provider: summary.data.provider,
        full_name: summary.data.full_name,
        default_branch: summary.data.default_branch,
        last_seen_sha: summary.data.last_seen_sha,
        open_findings: summary.data.open_findings,
        repair_count: summary.data.repair_count,
        last_job_at: summary.data.last_job_at,
        health_score: summary.data.health_score,
      }
    : {};

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 12,
        }}
      >
        <div className="col gap-1">
          <div className="row gap-2 muted" style={{ fontSize: "var(--t-12)" }}>
            <RepoIcon platform={repoFields.provider} s={12} />
            <span>{repoFields.provider || "—"}</span>
          </div>
          <div className="row gap-3" style={{ alignItems: "center" }}>
            <h1
              style={{
                margin: 0,
                fontSize: "var(--t-24)",
                letterSpacing: "-0.01em",
                fontWeight: 600,
              }}
            >
              {extractRepoName(repoFields.full_name) || "—"}
            </h1>
            {repoFields.default_branch && (
              <Pill tone="info">
                <Icon name="branch" s={11} /> {repoFields.default_branch}
              </Pill>
            )}
            {repoFields.last_seen_sha && (
              <span className="sha mono">
                {repoFields.last_seen_sha.slice(0, 7)}
              </span>
            )}
          </div>
          <p
            className="muted"
            style={{ margin: "4px 0 0", fontSize: "var(--t-13)" }}
          >
            {repoFields.full_name || "loading…"}
          </p>
        </div>
        <div className="row gap-2">
          <button
            className="btn"
            onClick={() => onOpenAudit?.("repo", repoId)}
          >
            <Icon name="audit" s={13} /> Audit
          </button>
          <button
            className="btn"
            onClick={() => syncRepos.mutate({ repo_id: repoId })}
            disabled={syncRepos.isPending}
          >
            <Icon name="retry" s={13} />
            {syncRepos.isPending ? " Syncing…" : " Re-sync"}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => onOpenRun?.(repoId)}
          >
            <Icon name="play" s={12} /> Run repair
          </button>
        </div>
      </div>

      <div
        className="card"
        style={{
          padding: 0,
          marginBottom: 12,
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
        }}
      >
        {[
          {
            l: "Health score",
            v: repoFields.health_score ?? "—",
          },
          {
            l: "Open findings",
            v: repoFields.open_findings ?? "—",
          },
          {
            l: "Repairs",
            v: repoFields.repair_count ?? "—",
          },
          {
            l: "Last job",
            v: repoFields.last_job_at
              ? new Date(repoFields.last_job_at).toLocaleString()
              : "—",
          },
        ].map((s, i) => (
          <div
            key={i}
            style={{
              padding: "14px 16px",
              borderRight: i < 3 ? "1px solid var(--hairline)" : "none",
            }}
          >
            <div
              className="muted"
              style={{
                fontSize: "var(--t-12)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                marginBottom: 4,
              }}
            >
              {s.l}
            </div>
            <div
              style={{
                fontSize: "var(--t-24)",
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}
            >
              {s.v}
            </div>
            {s.l === "Health score" &&
              typeof repoFields.health_score === "number" && (
                <HealthBar value={repoFields.health_score} />
              )}
          </div>
        ))}
      </div>

      <div className="tabs" style={{ marginBottom: 12 }}>
        {[
          { id: "overview", label: "Overview" },
          {
            id: "findings",
            label: "Findings",
            count: findings.data?.count ?? 0,
          },
          {
            id: "jobs",
            label: "Jobs",
            count: jobs.data?.count ?? 0,
          },
          { id: "config", label: ".selfrepair.yml" },
        ].map((t) => (
          <span
            key={t.id}
            className={`tab ${tab === t.id ? "is-active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.count != null && (
              <span className="tab-count">{t.count}</span>
            )}
          </span>
        ))}
      </div>

      {tab === "overview" && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr",
            gap: 12,
          }}
        >
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Top open findings</h2>
            </div>
            {findings.isLoading && (
              <div className="muted" style={{ padding: 8 }}>Loading…</div>
            )}
            {(findings.data?.items || []).slice(0, 8).map((f) => (
              <div
                key={f.id}
                className="row gap-3"
                style={{
                  padding: "8px 0",
                  borderBottom: "1px solid var(--hairline)",
                }}
              >
                <SeverityDot level={f.severity} />
                <span
                  className="mono"
                  style={{ flex: 1, fontSize: "var(--t-13)" }}
                >
                  {f.kind}
                </span>
                <span
                  className="faint mono"
                  style={{ fontSize: "var(--t-12)" }}
                >
                  {f.last_seen_at
                    ? new Date(f.last_seen_at).toLocaleDateString()
                    : ""}
                </span>
              </div>
            ))}
            {findings.data?.items?.length === 0 && (
              <div className="muted">No open findings.</div>
            )}
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Recent jobs</h2>
            </div>
            {jobs.isLoading && (
              <div className="muted" style={{ padding: 8 }}>Loading…</div>
            )}
            {(jobs.data?.items || []).slice(0, 8).map((j) => (
              <div
                key={j.id}
                className="row gap-3"
                style={{
                  padding: "8px 0",
                  borderBottom: "1px solid var(--hairline)",
                  cursor: "pointer",
                }}
                onClick={() => onNav("job", j.id)}
              >
                <StateBadge state={j.state} />
                <span
                  className="mono"
                  style={{ flex: 1, fontSize: "var(--t-13)" }}
                >
                  {j.id?.slice(0, 8)}
                </span>
                <span
                  className="mono muted"
                  style={{ fontSize: "var(--t-12)" }}
                >
                  {j.trigger}
                </span>
              </div>
            ))}
            {jobs.data?.items?.length === 0 && (
              <div className="muted">No jobs yet.</div>
            )}
          </div>
        </div>
      )}

      {tab === "findings" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {findings.isLoading && (
            <div className="muted" style={{ padding: 16 }}>Loading…</div>
          )}
          {findings.data?.items?.length === 0 && (
            <div className="muted" style={{ padding: 16 }}>
              No open findings.
            </div>
          )}
          {findings.data?.items?.length > 0 && (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 24 }}></th>
                  <th>Kind</th>
                  <th style={{ width: 120 }}>Severity</th>
                  <th style={{ width: 200 }}>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {findings.data.items.map((f) => (
                  <tr key={f.id}>
                    <td><SeverityDot level={f.severity} /></td>
                    <td className="mono">{f.kind}</td>
                    <td className="muted">{f.severity}</td>
                    <td className="muted">
                      {f.last_seen_at
                        ? new Date(f.last_seen_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "jobs" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {jobs.data?.items?.length > 0 ? (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Job</th>
                  <th style={{ width: 130 }}>Trigger</th>
                  <th style={{ width: 130 }}>State</th>
                  <th style={{ width: 200 }}>Started</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data.items.map((j) => (
                  <tr
                    key={j.id}
                    onClick={() => onNav("job", j.id)}
                  >
                    <td className="mono">{j.id?.slice(0, 8)}</td>
                    <td className="mono muted">{j.trigger}</td>
                    <td><StateBadge state={j.state} /></td>
                    <td className="muted">
                      {j.started_at
                        ? new Date(j.started_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="muted" style={{ padding: 16 }}>
              No jobs yet.
            </div>
          )}
        </div>
      )}

      {tab === "config" && (
        <div className="card" style={{ padding: 0 }}>
          <div
            className="row"
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--hairline)",
              justifyContent: "space-between",
            }}
          >
            <div className="row gap-2">
              <span className="mono" style={{ fontSize: "var(--t-13)" }}>
                .selfrepair.yml
              </span>
            </div>
          </div>
          <pre
            className="code"
            style={{
              margin: 0,
              borderRadius: 0,
              border: "none",
              padding: "14px 16px",
              lineHeight: 1.65,
              maxHeight: 520,
              overflow: "auto",
            }}
          >
            {summary.data?.config_yaml ||
              repo?.config_yaml ||
              "# .selfrepair.yml not configured for this repo yet."}
          </pre>
        </div>
      )}
    </div>
  );
};
