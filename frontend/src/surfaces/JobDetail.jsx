import React from "react";

import { Icon, Pill, StateBadge } from "../components/atoms.jsx";
import { useCancelJob, useJob, useJobEvents } from "../hooks/useJobs.js";
import { useJobEventStream } from "../hooks/useJobEventStream.js";

const LIVE_STATES = new Set([
  "queued", "cloning", "analyzing", "scanning", "planning",
  "repairing", "validating", "publishing",
]);

const STAGE_GROUPS = [
  { id: "discover", label: "Discover", states: ["queued", "cloning"], range: [0, 12] },
  { id: "analyze", label: "Analyze", states: ["analyzing", "scanning"], range: [12, 38] },
  { id: "heal", label: "Heal", states: ["planning", "repairing"], range: [38, 65] },
  { id: "validate", label: "Validate", states: ["validating", "failed_validation"], range: [65, 82] },
  { id: "report", label: "Report", states: ["publishing", "awaiting_review", "completed", "merged", "closed"], range: [82, 100] },
];

function stageStatus(currentState, stageId) {
  const idx = STAGE_GROUPS.findIndex((s) => s.id === stageId);
  for (let i = 0; i < STAGE_GROUPS.length; i++) {
    if (STAGE_GROUPS[i].states.includes(currentState)) {
      if (i > idx) return "ok";
      if (i === idx) return "run";
      return "idle";
    }
  }
  // Terminal state we haven't classified — treat as "all done".
  if (currentState === "escalated") return "idle";
  return "ok";
}

function formatDuration(startedAt, finishedAt) {
  if (!startedAt) return "—";
  const start = new Date(startedAt);
  const end = finishedAt ? new Date(finishedAt) : new Date();
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function relativeOffset(eventTs, baseTs) {
  if (!eventTs || !baseTs) return "";
  const ms = new Date(eventTs).getTime() - new Date(baseTs).getTime();
  if (Number.isNaN(ms)) return "";
  const sign = ms < 0 ? "-" : "+";
  const abs = Math.abs(ms);
  const sec = Math.floor(abs / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  const cs = Math.floor((abs % 1000) / 10);
  return `${sign}${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

function levelColor(level) {
  if (level === "ok") return "var(--ok)";
  if (level === "warn") return "var(--warn)";
  if (level === "error" || level === "err") return "var(--danger)";
  return "var(--fg-muted)";
}

export const JobDetail = ({ jobId, onNav, onOpenAudit }) => {
  const job = useJob(jobId);
  const history = useJobEvents(jobId, { limit: 1000 });
  const initialMaxId = history.data?.items?.length
    ? history.data.items[history.data.items.length - 1].id
    : 0;
  const stream = useJobEventStream(jobId, { since: initialMaxId });

  const allEvents = React.useMemo(() => {
    const h = history.data?.items || [];
    return h.concat(stream.events);
  }, [history.data, stream.events]);

  // "Pause" snapshots the current event count so new SSE messages
  // don't push the user's view forward. Resume returns to live tail.
  const [paused, setPaused] = React.useState(false);
  const [pausedLen, setPausedLen] = React.useState(null);
  const visible = paused && pausedLen !== null
    ? allEvents.slice(0, pausedLen)
    : allEvents;

  const currentState = job.data?.state || "queued";
  const isLive = LIVE_STATES.has(currentState);
  const baseTs = visible[0]?.ts || job.data?.started_at;

  const cancelJob = useCancelJob();

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}
      >
        <div>
          <div className="row gap-2 muted" style={{ fontSize: "var(--t-12)" }}>
            <span style={{ cursor: "pointer" }} onClick={() => onNav("jobs")}>Jobs</span>
            <Icon name="caret" s={11} />
            <span className="mono">{jobId}</span>
          </div>
          <div className="row gap-3" style={{ alignItems: "center", marginTop: 6 }}>
            <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }} className="mono">
              {jobId?.slice(0, 8) || "—"}
            </h1>
            <StateBadge state={currentState} />
            {job.data?.repo_id && (
              <span className="muted" style={{ fontSize: "var(--t-13)" }}>
                · repo {job.data.repo_id.slice(0, 8)}
              </span>
            )}
            {job.data?.trigger && (
              <span className="muted" style={{ fontSize: "var(--t-13)" }}>
                · trigger {job.data.trigger}
              </span>
            )}
          </div>
        </div>
        <div className="row gap-2">
          <button className="btn" onClick={() => onOpenAudit?.("job", jobId)}>
            <Icon name="audit" s={13} /> Audit log
          </button>
          <button
            className="btn"
            onClick={() => {
              if (paused) {
                setPaused(false);
                setPausedLen(null);
              } else {
                setPausedLen(allEvents.length);
                setPaused(true);
              }
            }}
          >
            <Icon name={paused ? "play" : "pause"} s={12} />
            {paused ? "Resume" : "Pause"}
          </button>
          {isLive && (
            <button
              className="btn btn-danger"
              onClick={() => cancelJob.mutate(jobId)}
              disabled={cancelJob.isPending}
            >
              {cancelJob.isPending ? "Cancelling…" : "Cancel job"}
            </button>
          )}
        </div>
      </div>

      <div className="row gap-3" style={{ marginBottom: 12 }}>
        {[
          { l: "Started", v: job.data?.started_at
              ? new Date(job.data.started_at).toLocaleString()
              : "—",
          },
          { l: "Duration",
            v: <span className="mono">{formatDuration(job.data?.started_at, job.data?.finished_at)}</span>,
          },
          { l: "State",
            v: <Pill tone={isLive ? "info" : "ok"} dot>{currentState}</Pill>,
          },
          { l: "Events",
            v: <span className="mono">{visible.length}</span>,
          },
          { l: "Stream",
            v: <Pill tone={stream.connected ? "ok" : "muted"} dot>{stream.connected ? "connected" : "disconnected"}</Pill>,
          },
        ].map((s, i) => (
          <div key={i} className="card" style={{ padding: "10px 14px", flex: 1 }}>
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
            <div style={{ fontSize: "var(--t-16)" }}>{s.v}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ padding: 14, marginBottom: 12 }}>
        <div className="h-section">
          <h2>Stage timeline</h2>
          <span className="faint mono" style={{ fontSize: "var(--t-12)" }}>{currentState}</span>
        </div>
        <div style={{ marginTop: 10 }}>
          {STAGE_GROUPS.map((g) => {
            const status = stageStatus(currentState, g.id);
            const [start, end] = g.range;
            return (
              <div key={g.id} className="stage-row">
                <span className="row gap-2">
                  <span
                    style={{
                      width: 8, height: 8, borderRadius: 999,
                      background:
                        status === "ok" ? "var(--ok)" :
                        status === "run" ? "var(--info)" :
                        "var(--fg-faint)",
                      boxShadow:
                        status === "run" ? "0 0 0 4px rgba(59,130,246,0.18)" : "none",
                    }}
                  />
                  <span style={{ fontSize: "var(--t-13)" }}>{g.label}</span>
                </span>
                <div className="stage-bar">
                  <div
                    className={`stage-fill ${status}`}
                    style={{ left: `${start}%`, width: `${end - start}%` }}
                  />
                </div>
                <span
                  className="mono muted"
                  style={{ fontSize: "var(--t-12)", textAlign: "right" }}
                >
                  {(end - start)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 12 }}>
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
              <h2 style={{ margin: 0, fontSize: "var(--t-13)", fontWeight: 600 }}>
                Event stream
              </h2>
              {!paused && stream.connected && (
                <span className="live" style={{ fontSize: 10 }}>streaming</span>
              )}
            </div>
            <div className="row gap-2">
              <span className="chip">all</span>
              <span className="chip">errors</span>
              <button className="btn btn-sm">Export</button>
            </div>
          </div>
          <div
            style={{
              maxHeight: 380,
              overflow: "auto",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--t-12)",
            }}
          >
            {history.isLoading && (
              <div className="muted" style={{ padding: 12 }}>Loading history…</div>
            )}
            {visible.map((e) => {
              const offset = relativeOffset(e.ts, baseTs);
              return (
                <div
                  key={e.id}
                  className="row gap-3 stream-in"
                  style={{
                    padding: "5px 14px",
                    borderBottom: "1px solid var(--hairline)",
                    lineHeight: 1.5,
                  }}
                >
                  <span className="faint" style={{ width: 80 }}>{offset}</span>
                  <span
                    style={{
                      width: 38,
                      color: levelColor(e.level),
                      fontWeight: 600,
                      textTransform: "uppercase",
                      fontSize: 10.5,
                    }}
                  >
                    {e.level}
                  </span>
                  <span className="mono" style={{ width: 80, color: "var(--fg-muted)" }}>
                    {e.stage}
                  </span>
                  <span style={{ flex: 1, color: "var(--fg)" }}>{e.message}</span>
                </div>
              );
            })}
            {!paused && isLive && stream.connected && (
              <div
                className="row gap-2"
                style={{ padding: "8px 14px", color: "var(--cyan)" }}
              >
                <span
                  className="pulse"
                  style={{ width: 6, height: 6, borderRadius: 999, background: "var(--cyan)" }}
                />
                <span>waiting for next event…</span>
              </div>
            )}
            {!stream.connected && isLive && (
              <div className="muted" style={{ padding: "8px 14px" }}>
                live tail disconnected — will reconnect automatically.
              </div>
            )}
          </div>
        </div>

        <div className="col gap-3">
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section"><h2>Job</h2></div>
            <div className="col gap-2">
              <div className="row gap-3" style={{ padding: "4px 0", fontSize: "var(--t-13)" }}>
                <span className="muted" style={{ width: 90 }}>ID</span>
                <span className="mono">{jobId}</span>
              </div>
              <div className="row gap-3" style={{ padding: "4px 0", fontSize: "var(--t-13)" }}>
                <span className="muted" style={{ width: 90 }}>Sandbox</span>
                <span className="mono">{job.data?.sandbox_id || "—"}</span>
              </div>
              <div className="row gap-3" style={{ padding: "4px 0", fontSize: "var(--t-13)" }}>
                <span className="muted" style={{ width: 90 }}>Finished</span>
                <span className="mono">
                  {job.data?.finished_at
                    ? new Date(job.data.finished_at).toLocaleString()
                    : "—"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
