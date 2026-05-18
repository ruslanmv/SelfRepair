import React from "react";

import { Icon } from "../components/atoms.jsx";
import { useJobEventStream } from "../hooks/useJobEventStream.js";
import { useCreateJob, useJob } from "../hooks/useJobs.js";
import { useRepos } from "../hooks/useRepos.js";

// Visual steps the modal narrates. Each step maps to a window of JobStates;
// the active step is derived from the live job state once the worker
// starts processing. The pre-run "policy" step is purely UI — it lights
// up while the API enqueues — and isn't a real JobState.
const REPAIR_STEPS = [
  { id: "policy", label: "Policy gate", icon: "shield", desc: "Enqueued · waiting for worker", states: ["queued"] },
  { id: "discover", label: "Discover", icon: "search", desc: "Clone · layout · standards", states: ["cloning"] },
  { id: "analyze", label: "Analyze", icon: "findings", desc: "Detect findings · fingerprint", states: ["analyzing", "scanning"] },
  { id: "plan", label: "Plan strategy", icon: "spark", desc: "auto-fix · llm-assist", states: ["planning"] },
  { id: "sandbox", label: "Sandbox", icon: "shield", desc: "Hermetic image · validate", states: ["repairing", "validating"] },
  { id: "sign", label: "Sign & attest", icon: "check", desc: "Sigstore · provenance", states: ["publishing"] },
  { id: "open", label: "Open repair PR", icon: "branch", desc: "Awaiting human approval", states: ["awaiting_review", "completed", "merged", "closed"] },
];

const TERMINAL_STATES = new Set([
  "completed", "merged", "closed", "stale", "escalated", "failed_validation",
]);

function activeStepIndex(state) {
  if (!state) return 0;
  for (let i = 0; i < REPAIR_STEPS.length; i++) {
    if (REPAIR_STEPS[i].states.includes(state)) return i;
  }
  return REPAIR_STEPS.length - 1;
}

function levelColor(lvl) {
  if (lvl === "ok") return "var(--ok)";
  if (lvl === "warn") return "var(--warn)";
  if (lvl === "error" || lvl === "err") return "var(--danger)";
  return "var(--cyan)";
}

export const RunRepairModal = ({ open, onClose, onNav, defaultRepo }) => {
  const repos = useRepos({ limit: 200 });
  const createJob = useCreateJob();

  const [phase, setPhase] = React.useState("config"); // config -> run -> done
  const [repoId, setRepoId] = React.useState("");
  const [trigger, setTrigger] = React.useState("manual");
  const [jobId, setJobId] = React.useState(null);
  const [submitError, setSubmitError] = React.useState(null);

  const job = useJob(phase === "run" || phase === "done" ? jobId : null);
  const stream = useJobEventStream(
    phase === "run" || phase === "done" ? jobId : null,
  );
  const logEndRef = React.useRef(null);

  React.useEffect(() => {
    if (open) {
      setPhase("config");
      setJobId(null);
      setSubmitError(null);
      // Default selection: prefer the value the caller passed in (which
      // can be a UUID or a full_name); else first repo from the API.
      const items = repos.data?.items || [];
      const matched = items.find(
        (r) => r.id === defaultRepo || r.full_name === defaultRepo,
      );
      setRepoId(matched?.id || items[0]?.id || "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultRepo, repos.data?.items?.length]);

  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "end" });
  }, [stream.events.length]);

  React.useEffect(() => {
    if (phase === "run" && job.data && TERMINAL_STATES.has(job.data.state)) {
      setPhase("done");
    }
  }, [phase, job.data]);

  if (!open) return null;

  const currentState = job.data?.state;
  const active = activeStepIndex(currentState);
  const done = phase === "done";

  const submit = async () => {
    if (!repoId) return;
    setSubmitError(null);
    try {
      const result = await createJob.mutateAsync({
        repo_id: repoId,
        trigger,
      });
      setJobId(result.job_id);
      setPhase("run");
    } catch (err) {
      setSubmitError(err?.detail || err?.message || "Failed to start job");
    }
  };

  return (
    <div className="cmd-overlay" onClick={onClose} style={{ paddingTop: "6vh" }}>
      <div className="run-modal" onClick={(e) => e.stopPropagation()}>
        <div className="run-head">
          <div className="row gap-3">
            <span
              className="run-pulse"
              data-state={done ? "done" : phase === "run" ? "run" : "idle"}
            >
              <span /><span /><span />
            </span>
            <div className="col">
              <h2 style={{ margin: 0, fontSize: "var(--t-16)", fontWeight: 600 }}>
                {phase === "config"
                  ? "Run repair"
                  : phase === "run"
                    ? "Repair in progress…"
                    : "Repair complete"}
              </h2>
              <span className="muted mono" style={{ fontSize: "var(--t-12)" }}>
                {jobId
                  ? `job ${jobId.slice(0, 8)}`
                  : repos.data?.items?.find((r) => r.id === repoId)?.full_name || ""}
              </span>
            </div>
          </div>
          <div className="row gap-2">
            <button className="btn btn-sm btn-ghost" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        {phase === "config" && (
          <div style={{ padding: 18 }}>
            <div
              className="muted"
              style={{
                fontSize: "var(--t-12)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: 6,
              }}
            >
              Repository
            </div>
            <select
              value={repoId}
              onChange={(e) => setRepoId(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", marginBottom: 14 }}
            >
              {repos.isLoading && <option>Loading repos…</option>}
              {(repos.data?.items || []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name}
                </option>
              ))}
              {repos.data?.items?.length === 0 && (
                <option value="">No repos available — connect one in Settings.</option>
              )}
            </select>

            <div
              className="muted"
              style={{
                fontSize: "var(--t-12)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: 8,
              }}
            >
              Trigger
            </div>
            <div className="row gap-2" style={{ marginBottom: 12 }}>
              {["manual", "scheduled", "retry"].map((t) => (
                <span
                  key={t}
                  className={`chip ${trigger === t ? "is-active" : ""}`}
                  onClick={() => setTrigger(t)}
                >
                  {t}
                </span>
              ))}
            </div>

            {submitError && (
              <div
                role="alert"
                style={{
                  marginTop: 10,
                  padding: "8px 10px",
                  borderRadius: 6,
                  background: "rgba(220, 50, 70, 0.12)",
                  color: "var(--danger, #f06d75)",
                  fontSize: 13,
                }}
              >
                {submitError}
              </div>
            )}

            <div
              className="row gap-2"
              style={{ marginTop: 18, justifyContent: "flex-end" }}
            >
              <button className="btn" onClick={onClose}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={submit}
                disabled={!repoId || createJob.isPending}
              >
                <Icon name="play" s={12} />
                {createJob.isPending ? " Starting…" : " Run repair"}
              </button>
            </div>
          </div>
        )}

        {phase !== "config" && (
          <>
            <div className="step-rail">
              {REPAIR_STEPS.map((s, i) => {
                const state =
                  i < active
                    ? "done"
                    : i === active
                      ? done
                        ? "done"
                        : "active"
                      : "idle";
                return (
                  <React.Fragment key={s.id}>
                    <div className={`step-node state-${state}`}>
                      <span className="step-ico">
                        <Icon
                          name={state === "done" ? "check" : s.icon}
                          s={13}
                        />
                      </span>
                      <div className="col">
                        <span style={{ fontSize: "var(--t-12)", fontWeight: 600 }}>
                          {s.label}
                        </span>
                        <span className="faint" style={{ fontSize: 10.5 }}>
                          {s.desc}
                        </span>
                      </div>
                    </div>
                    {i < REPAIR_STEPS.length - 1 && (
                      <span
                        className={`step-line state-${
                          i < active ? "done" : "idle"
                        }`}
                      />
                    )}
                  </React.Fragment>
                );
              })}
            </div>

            <div className="run-log">
              {stream.events.length === 0 && !done && (
                <div className="muted" style={{ padding: "12px 14px" }}>
                  Waiting for first event from worker…
                </div>
              )}
              {stream.events.map((e) => (
                <div key={e.id} className="run-log-row stream-in">
                  <span className="faint mono" style={{ width: 80 }}>
                    {e.ts ? new Date(e.ts).toLocaleTimeString() : ""}
                  </span>
                  <span
                    className="mono"
                    style={{
                      width: 38,
                      color: levelColor(e.level),
                      fontWeight: 700,
                      textTransform: "uppercase",
                      fontSize: 10,
                    }}
                  >
                    {e.level}
                  </span>
                  <span
                    className="mono"
                    style={{ width: 80, color: "var(--fg-muted)" }}
                  >
                    {e.stage}
                  </span>
                  <span className="mono" style={{ flex: 1 }}>
                    {e.message}
                  </span>
                </div>
              ))}
              {!done && phase === "run" && stream.connected && (
                <div className="run-log-row" style={{ color: "var(--cyan)" }}>
                  <span className="pulse mono" style={{ width: 80 }}>···</span>
                  <span className="mono">streaming next event…</span>
                </div>
              )}
              <div ref={logEndRef} />
            </div>

            <div className="run-foot">
              <div
                className="row gap-3 grow muted"
                style={{ fontSize: "var(--t-12)" }}
              >
                <span>state {currentState || "—"}</span>
                <span>·</span>
                <span>{stream.events.length} events</span>
                <span>·</span>
                <span>
                  {stream.connected ? "live tail" : "reconnecting…"}
                </span>
              </div>
              <div className="row gap-2">
                {jobId && (
                  <button
                    className="btn"
                    onClick={() => {
                      onClose();
                      onNav("job", jobId);
                    }}
                  >
                    Open job
                  </button>
                )}
                {done && (
                  <button
                    className="btn btn-primary"
                    onClick={() => {
                      onClose();
                      onNav("repairs");
                    }}
                  >
                    Review repairs →
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
