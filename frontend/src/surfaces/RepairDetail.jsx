import React from "react";

import {
  Icon,
  Pill,
  SeverityDot,
  StateBadge,
} from "../components/atoms.jsx";
import {
  useApproveRepair,
  usePublishPr,
  useRejectRepair,
  useRepair,
  useRepairDiff,
  useRerunValidation,
} from "../hooks/useRepairs.js";

export const RepairDetail = ({ repairId, onNav, onOpenAudit }) => {
  const repair = useRepair(repairId);
  const diff = useRepairDiff(repairId);
  const approve = useApproveRepair();
  const reject = useRejectRepair();
  const rerun = useRerunValidation();
  const publish = usePublishPr();
  const [tab, setTab] = React.useState("summary");

  const r = repair.data || {};
  const policyDecisions = r.policy_decisions || [];
  const provenance = r.provenance;
  const sandbox = diff.data?.sandbox_result;

  const cost = `$${(r.cost_usd ?? 0).toFixed(3)}`;

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <div className="row gap-2 muted" style={{ fontSize: "var(--t-12)" }}>
            <span
              style={{ cursor: "pointer" }}
              onClick={() => onNav("repairs")}
            >
              Repairs
            </span>
            <Icon name="caret" s={11} />
            <span className="mono">{repairId}</span>
          </div>
          <div
            className="row gap-3"
            style={{ alignItems: "center", marginTop: 6 }}
          >
            <h1
              style={{
                margin: 0,
                fontSize: "var(--t-24)",
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}
            >
              {r.fixer_id || "—"}
            </h1>
          </div>
          <div
            className="row gap-2"
            style={{ marginTop: 8, fontSize: "var(--t-13)" }}
          >
            <StateBadge state={r.state} />
            <span className="muted">·</span>
            <span className="muted">
              {r.repo?.full_name || (r.job?.id ? `job ${r.job.id.slice(0, 8)}` : "—")}
            </span>
            <span className="muted">· mode {r.mode}</span>
            <span className="muted">· cost {cost}</span>
            {r.created_at && (
              <span className="muted">
                · created {new Date(r.created_at).toLocaleString()}
              </span>
            )}
          </div>
        </div>
        <div className="row gap-2">
          <button
            className="btn"
            onClick={() => onOpenAudit?.("repair", repairId)}
          >
            <Icon name="audit" s={13} /> Audit log
          </button>
          <button
            className="btn"
            onClick={() => rerun.mutate(repairId)}
            disabled={rerun.isPending}
          >
            {rerun.isPending ? "Rerunning…" : "Rerun validation"}
          </button>
          <button
            className="btn btn-danger"
            onClick={() =>
              reject.mutate({ id: repairId, body: { rule_id: "manual.review" } })
            }
            disabled={reject.isPending}
          >
            {reject.isPending ? "Rejecting…" : "Reject"}
          </button>
          <button
            className="btn btn-primary"
            onClick={() =>
              approve.mutate({ id: repairId, body: { rule_id: "manual.review" } })
            }
            disabled={approve.isPending}
          >
            <Icon name="check" s={13} />
            {approve.isPending ? " Approving…" : " Approve"}
          </button>
          <button
            className="btn"
            onClick={() => publish.mutate(repairId)}
            disabled={publish.isPending}
          >
            {publish.isPending ? "Publishing…" : "Publish PR"}
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
            l: "State",
            v: r.state || "—",
            tone: r.state === "merged" ? "ok" : "info",
          },
          {
            l: "Mode",
            v: r.mode || "—",
            tone: "info",
          },
          {
            l: "Signed",
            v: r.signed_commit_sha
              ? r.signed_commit_sha.slice(0, 12)
              : "—",
            tone: r.signed_commit_sha ? "ok" : "warn",
          },
          {
            l: "Cost",
            v: cost,
            tone: "info",
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
                fontSize: "var(--t-20)",
                fontWeight: 600,
                color: s.tone ? `var(--${s.tone})` : undefined,
              }}
            >
              {s.v}
            </div>
          </div>
        ))}
      </div>

      <div className="tabs" style={{ marginBottom: 12 }}>
        {[
          { id: "summary", label: "Summary" },
          { id: "diff", label: "Diff" },
          {
            id: "policy",
            label: "Policy trace",
            count: policyDecisions.length,
          },
          { id: "sandbox", label: "Sandbox" },
          { id: "provenance", label: "Provenance" },
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

      {tab === "summary" && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Finding</h2>
            </div>
            {r.finding ? (
              <div className="row gap-2" style={{ marginTop: 6 }}>
                <SeverityDot level={r.finding.severity} />
                <div className="col grow">
                  <span
                    className="mono"
                    style={{ fontSize: "var(--t-13)" }}
                  >
                    {r.finding.kind}
                  </span>
                  <span
                    className="faint mono"
                    style={{ fontSize: "var(--t-12)" }}
                  >
                    {r.finding.fingerprint?.slice(0, 16)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="muted">Linked finding not loaded yet.</div>
            )}
          </div>
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Job</h2>
            </div>
            {r.job ? (
              <div
                className="row gap-2"
                style={{ marginTop: 6, cursor: "pointer" }}
                onClick={() => onNav("job", r.job.id)}
              >
                <StateBadge state={r.job.state} />
                <span className="mono" style={{ flex: 1 }}>
                  {r.job.id?.slice(0, 8)}
                </span>
                <span className="muted">{r.job.trigger}</span>
              </div>
            ) : (
              <div className="muted">No linked job.</div>
            )}
          </div>
        </div>
      )}

      {tab === "diff" && (
        <div className="card" style={{ padding: 14 }}>
          <div className="h-section">
            <h2>Diff</h2>
            {r.diff_sha && (
              <span className="mono faint" style={{ fontSize: "var(--t-12)" }}>
                sha {r.diff_sha.slice(0, 12)}
              </span>
            )}
          </div>
          {diff.isLoading && <div className="muted">Loading…</div>}
          {!diff.isLoading && !diff.data?.diff_sha && (
            <div className="muted">
              No diff has been recorded for this repair yet.
            </div>
          )}
          {diff.data?.diff_sha && !diff.data?.diff && (
            <div className="muted">
              Diff bytes are stored in object storage and will be served once
              the artifact endpoint lands (M6).
            </div>
          )}
        </div>
      )}

      {tab === "policy" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {policyDecisions.length === 0 ? (
            <div className="muted" style={{ padding: 16 }}>
              No policy decisions recorded.
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th style={{ width: 120 }}>Outcome</th>
                  <th style={{ width: 140 }}>Approval</th>
                  <th style={{ width: 200 }}>Decided</th>
                </tr>
              </thead>
              <tbody>
                {policyDecisions.map((d) => (
                  <tr key={d.id}>
                    <td className="mono">{d.rule_id}</td>
                    <td>
                      <Pill
                        tone={
                          d.outcome === "allow"
                            ? "ok"
                            : d.outcome === "deny"
                              ? "danger"
                              : "info"
                        }
                      >
                        {d.outcome}
                      </Pill>
                    </td>
                    <td className="muted">
                      {d.requires_approval ? "required" : "not required"}
                    </td>
                    <td className="muted">{d.decided_at || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "sandbox" && (
        <div
          className="card"
          style={{
            padding: 14,
            fontFamily: "var(--font-mono)",
            fontSize: "var(--t-12)",
            whiteSpace: "pre-wrap",
          }}
        >
          {sandbox
            ? JSON.stringify(sandbox, null, 2)
            : "No sandbox result recorded yet."}
        </div>
      )}

      {tab === "provenance" && (
        <div className="card" style={{ padding: 14 }}>
          {provenance ? (
            <div className="col gap-2" style={{ fontSize: "var(--t-13)" }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="muted">Builder</span>
                <span className="mono">{provenance.builder}</span>
              </div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="muted">Created</span>
                <span className="mono">{provenance.created_at}</span>
              </div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="muted">Attestation</span>
                <span className="mono">
                  {provenance.has_attestation
                    ? `${provenance.attestation_size} bytes`
                    : "none"}
                </span>
              </div>
              <div
                className="hairline-t"
                style={{ marginTop: 8, paddingTop: 8 }}
              >
                <pre className="code" style={{ margin: 0 }}>
                  {JSON.stringify(provenance.materials, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <div className="muted">No provenance recorded yet.</div>
          )}
        </div>
      )}
    </div>
  );
};
