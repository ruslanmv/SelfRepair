import React from "react";

import { Icon, Pill, SeverityDot } from "../components/atoms.jsx";
import {
  useOrgReviewSettings,
  usePutOrgReviewSettings,
  useRemediations,
  useRequestRemediation,
  useRetryReview,
  useReview,
  useReviewFindings,
  useReviews,
} from "../hooks/useReviews.js";

// Check conclusions come from `policy.conclude`; this screen only shows them.
const CONCLUSION_TONE = {
  success: "ok",
  failure: "danger",
  action_required: "warn",
  neutral: "neutral",
  cancelled: "neutral",
};
const RETRYABLE = new Set(["incomplete", "failed", "queued"]);
const short = (sha) => (sha ? sha.slice(0, 8) : "—");
const when = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

const Conclusion = ({ run }) => (
  <Pill tone={CONCLUSION_TONE[run.conclusion] || "info"} dot>
    {run.conclusion || run.status}
  </Pill>
);

const Panel = ({ children }) => (
  <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 14 }}>
    {children}
  </div>
);

const Note = ({ children, danger }) => (
  <div className="muted" style={{ padding: 16, color: danger ? "var(--danger)" : undefined }}>
    {children}
  </div>
);

function ReviewList({ onOpen }) {
  const { data, isLoading, isError, error } = useReviews({ limit: 100 });
  const items = data?.items || [];
  return (
    <Panel>
      {isLoading && <Note>Loading…</Note>}
      {isError && <Note danger>{error?.detail || "Could not load reviews"}</Note>}
      {!isLoading && !isError && items.length === 0 && (
        <Note>
          No reviews yet. Reviews are off until an organization or repository sets
          <code> reviewer.enabled: true</code>.
        </Note>
      )}
      {items.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 150 }}>Result</th>
              <th>Change</th>
              <th style={{ width: 120 }}>Event</th>
              <th style={{ width: 120 }}>Engine</th>
              <th style={{ width: 180 }}>Started</th>
            </tr>
          </thead>
          <tbody>
            {items.map((run) => (
              <tr
                key={run.id}
                onClick={() => onOpen(run.id)}
                style={{ cursor: "pointer" }}
                data-testid="review-row"
              >
                <td><Conclusion run={run} /></td>
                <td>
                  <div className="mono" style={{ fontSize: "var(--t-12)" }}>
                    {short(run.base_sha)} → {short(run.head_sha)}
                    {run.pr_number ? ` · #${run.pr_number}` : ""}
                  </div>
                  <div className="muted" style={{ fontSize: "var(--t-12)" }}>
                    {run.ref || ""}
                  </div>
                </td>
                <td>{run.provider} · {run.event_type}</td>
                <td>{run.engine}</td>
                <td className="muted">{when(run.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function OrgSettings() {
  const { data, isLoading, isError, error } = useOrgReviewSettings();
  const save = usePutOrgReviewSettings();
  const [text, setText] = React.useState("");
  const [message, setMessage] = React.useState("");
  React.useEffect(() => {
    if (data?.config) setText(JSON.stringify(data.config, null, 2));
  }, [data]);
  const submit = async () => {
    setMessage("");
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      setMessage("Settings must be valid JSON.");
      return;
    }
    try {
      await save.mutateAsync(parsed);
      setMessage("Saved. Repository files and per-repository overrides still apply on top.");
    } catch (err) {
      setMessage(typeof err?.detail === "string" ? err.detail : "Could not save settings");
    }
  };
  return (
    <Panel>
      <div style={{ padding: 16 }}>
        <h2 style={{ margin: "0 0 4px", fontSize: "var(--t-16)", fontWeight: 600 }}>
          Organization review defaults
        </h2>
        <p className="muted" style={{ margin: "0 0 10px", fontSize: "var(--t-13)" }}>
          Order of precedence: defaults, this organization setting, <code>.selfrepair.yml</code>,
          per-repository override. <code>read_only</code> and <code>auto_merge: false</code> cannot
          be changed.
        </p>
        {isLoading && <div className="muted">Loading…</div>}
        {isError && <div style={{ color: "var(--danger)" }}>{error?.detail || "Could not load"}</div>}
        {!isLoading && !isError && (
          <>
            <textarea
              className="input mono"
              aria-label="Organization reviewer settings"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={16}
              style={{ width: "100%", fontSize: "var(--t-12)", height: "auto" }}
            />
            <div className="row gap-2" style={{ marginTop: 8, alignItems: "center" }}>
              <button className="btn btn-primary" onClick={submit} disabled={save.isPending}>
                Save defaults
              </button>
              {message && <span className="muted" role="status">{message}</span>}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

function RemediationTasks({ reviewId }) {
  const { data } = useRemediations(reviewId);
  const items = data?.items || [];
  if (!items.length) return null;
  return (
    <Panel>
      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 170 }}>GitPilot task</th>
            <th style={{ width: 110 }}>Mode</th>
            <th style={{ width: 160 }}>Status</th>
            <th>Paths · result</th>
          </tr>
        </thead>
        <tbody>
          {items.map((task) => (
            <tr key={task.id}>
              <td className="mono" style={{ fontSize: "var(--t-12)" }}>{task.id.slice(-12)}</td>
              <td>{task.mode}{task.approved ? " ✓" : ""}</td>
              <td>
                <Pill
                  tone={
                    task.status === "completed"
                      ? "ok"
                      : ["failed", "blocked", "gitpilot_unavailable"].includes(task.status)
                        ? "danger"
                        : "info"
                  }
                  dot
                >
                  {task.status}
                </Pill>
              </td>
              <td>
                <div className="mono" style={{ fontSize: "var(--t-12)" }}>
                  {(task.allowed_paths || []).join(", ")}
                </div>
                <div className="muted" style={{ fontSize: "var(--t-12)" }}>
                  {task.error ||
                    (task.result?.warnings || []).join("; ") ||
                    (task.result?.pr_url ? `Draft PR: ${task.result.pr_url}` : "")}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function ReviewDetail({ reviewId, onBack }) {
  const review = useReview(reviewId);
  const findings = useReviewFindings(reviewId);
  const retry = useRetryReview();
  const remediate = useRequestRemediation();
  const [notice, setNotice] = React.useState("");

  if (review.isLoading) return <Note>Loading…</Note>;
  if (review.isError) {
    return (
      <Panel>
        <Note danger>
          {review.error?.status === 404
            ? "This review does not exist in your organization."
            : review.error?.detail || "Could not load review"}
        </Note>
        <div style={{ padding: "0 16px 16px" }}>
          <button className="btn" onClick={onBack}>Back to reviews</button>
        </div>
      </Panel>
    );
  }
  const run = review.data;
  const items = findings.data?.items || [];

  const doRetry = async () => {
    setNotice("");
    try {
      const out = await retry.mutateAsync(run.id);
      setNotice(`Retry ${out.outcome}.`);
    } catch (err) {
      setNotice(typeof err?.detail === "string" ? err.detail : "Retry failed");
    }
  };
  const dryRun = async (fingerprint) => {
    setNotice("");
    try {
      const out = await remediate.mutateAsync({
        id: run.id,
        body: { fingerprints: [fingerprint] },
      });
      setNotice(`GitPilot dry run ${out.outcome}.`);
    } catch (err) {
      setNotice(typeof err?.detail === "string" ? err.detail : "Remediation refused");
    }
  };

  return (
    <>
      <Panel>
        <div style={{ padding: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <div className="row gap-2" style={{ alignItems: "center" }}>
              <Conclusion run={run} />
              <span className="mono">{short(run.base_sha)} → {short(run.head_sha)}</span>
              {run.pr_number ? <span className="muted">#{run.pr_number}</span> : null}
            </div>
            <div className="row gap-2">
              <button className="btn" onClick={onBack}>Back</button>
              <button
                className="btn btn-primary"
                onClick={doRetry}
                disabled={!RETRYABLE.has(run.status) || retry.isPending}
                title={RETRYABLE.has(run.status) ? "" : "Only incomplete or failed runs can be retried"}
              >
                Retry
              </button>
            </div>
          </div>
          <div className="muted" style={{ marginTop: 8, fontSize: "var(--t-13)" }}>
            {run.provider} · {run.event_type} · {run.ref || ""} · engine {run.engine}
            {run.model_id ? ` (${run.model_id})` : ""} · policy v{run.policy_version} · status{" "}
            {run.status}
          </div>
          {run.error && (
            <div style={{ marginTop: 8, color: "var(--danger)", fontSize: "var(--t-13)" }}>
              {run.error}
            </div>
          )}
          {run.summary && (
            <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: "var(--t-12)", marginTop: 10 }}>
              {run.summary}
            </pre>
          )}
          {notice && <div role="status" className="muted" style={{ marginTop: 8 }}>{notice}</div>}
        </div>
      </Panel>
      <Panel>
        {findings.isLoading && <Note>Loading findings…</Note>}
        {!findings.isLoading && items.length === 0 && (
          <Note>No findings. A clean review is a valid result.</Note>
        )}
        {items.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 28 }}>Sev</th>
                <th>Finding</th>
                <th style={{ width: 260 }}>Location</th>
                <th style={{ width: 110 }}>Source</th>
                <th style={{ width: 120 }} />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.fingerprint} data-testid="review-finding">
                  <td><SeverityDot level={item.severity} /></td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{item.title}</div>
                    <div className="muted" style={{ fontSize: "var(--t-12)" }}>
                      {item.category} · {item.description}
                    </div>
                  </td>
                  <td className="mono" style={{ fontSize: "var(--t-12)" }}>
                    {item.file_path || "—"}
                    {item.start_line ? `:${item.start_line}` : ""}
                  </td>
                  <td>{item.source}</td>
                  <td>
                    {item.file_path && item.validation_state === "accepted" && (
                      <button
                        className="btn btn-ghost"
                        onClick={() => dryRun(item.fingerprint)}
                        disabled={remediate.isPending}
                        title="Send to GitPilot POST /repair as a dry run"
                      >
                        Dry-run fix
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <RemediationTasks reviewId={run.id} />
    </>
  );
}

export const Reviews = ({ reviewId, onNav }) => {
  const [tab, setTab] = React.useState("runs");
  const open = (id) => onNav("review", id);
  const back = () => onNav("reviews");
  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
            <Icon name="audit" s={18} /> Reviews
          </h1>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
            Check <code>SelfRepair / Review</code> on pushes, pull requests and merge requests
          </p>
        </div>
        {!reviewId && (
          <div className="row gap-2">
            <span className={`chip ${tab === "runs" ? "is-active" : ""}`} onClick={() => setTab("runs")}>
              Runs
            </span>
            <span
              className={`chip ${tab === "settings" ? "is-active" : ""}`}
              onClick={() => setTab("settings")}
            >
              Settings
            </span>
          </div>
        )}
      </div>
      {reviewId ? (
        <ReviewDetail reviewId={reviewId} onBack={back} />
      ) : tab === "settings" ? (
        <OrgSettings />
      ) : (
        <ReviewList onOpen={open} />
      )}
    </div>
  );
};
