import React from "react";

import { Icon, Pill, StateBadge } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const JobDetail = ({ jobId, onNav, onOpenAudit }) => {
  const job = D.jobs.find((j) => j.id === jobId) || D.jobs[0];
  const [streamIdx, setStreamIdx] = React.useState(8);
  const [playing, setPlaying] = React.useState(true);
  const events = D.liveEvents.slice(0, streamIdx);

  React.useEffect(() => {
    if (!playing) return;
    if (streamIdx >= D.liveEvents.length) return;
    const t = setTimeout(() => setStreamIdx((i) => i + 1), 900);
    return () => clearTimeout(t);
  }, [streamIdx, playing]);

  const stages = [
    { id: "discover", label: "Discover", state: "ok", start: 0, end: 5 },
    { id: "analyze", label: "Analyze", state: "ok", start: 5, end: 30 },
    { id: "heal", label: "Heal", state: streamIdx > 7 ? "ok" : "run", start: 30, end: 55 },
    { id: "validate", label: "Validate", state: streamIdx > 13 ? "ok" : streamIdx > 10 ? "run" : "idle", start: 55, end: 80 },
    { id: "report", label: "Report", state: streamIdx > 15 ? "ok" : streamIdx > 13 ? "run" : "idle", start: 80, end: 100 },
  ];

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div>
          <div className="row gap-2 muted" style={{ fontSize: "var(--t-12)" }}>
            <span style={{ cursor: "pointer" }} onClick={() => onNav("jobs")}>Jobs</span>
            <Icon name="caret" s={11} />
            <span className="mono">{job.id}</span>
          </div>
          <div className="row gap-3" style={{ alignItems: "center", marginTop: 6 }}>
            <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }} className="mono">{job.id}</h1>
            <StateBadge state={streamIdx >= D.liveEvents.length ? "succeeded" : "running"} />
            <span className="muted" style={{ fontSize: "var(--t-13)" }}>· {job.repo}</span>
            <span className="muted" style={{ fontSize: "var(--t-13)" }}>· trigger {job.trigger}</span>
          </div>
        </div>
        <div className="row gap-2">
          <button className="btn" onClick={() => onOpenAudit?.("job", job.id)}><Icon name="audit" s={13} /> Audit log</button>
          <button className="btn" onClick={() => { setStreamIdx(8); setPlaying(true); }}><Icon name="retry" s={13} /> Replay</button>
          <button className="btn" onClick={() => setPlaying((p) => !p)}>
            <Icon name={playing ? "pause" : "play"} s={12} />
            {playing ? "Pause" : "Play"}
          </button>
          <button className="btn btn-danger">Cancel job</button>
        </div>
      </div>

      <div className="row gap-3" style={{ marginBottom: 12 }}>
        {[
          { l: "Started", v: "12:42:08 UTC" },
          { l: "Duration", v: <span className="mono">{job.duration}</span> },
          { l: "Stage", v: <Pill tone="info" dot>{stages.find((s) => s.state === "run")?.label || "report"}</Pill> },
          { l: "Events", v: <span className="mono">{events.length}/{D.liveEvents.length}</span> },
          { l: "Cost", v: <span className="mono">$0.024</span> },
        ].map((s, i) => (
          <div key={i} className="card" style={{ padding: "10px 14px", flex: 1 }}>
            <div className="muted" style={{ fontSize: "var(--t-12)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>{s.l}</div>
            <div style={{ fontSize: "var(--t-16)" }}>{s.v}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ padding: 14, marginBottom: 12 }}>
        <div className="h-section"><h2>Stage timeline</h2><span className="faint mono" style={{ fontSize: "var(--t-12)" }}>0:00 → 0:02.08</span></div>
        <div style={{ marginTop: 10 }}>
          {stages.map((s, i) => (
            <div key={i} className="stage-row">
              <span className="row gap-2">
                <span style={{ width: 8, height: 8, borderRadius: 999, background: s.state === "ok" ? "var(--ok)" : s.state === "run" ? "var(--info)" : "var(--fg-faint)", boxShadow: s.state === "run" ? "0 0 0 4px rgba(59,130,246,0.18)" : "none" }} />
                <span style={{ fontSize: "var(--t-13)" }}>{s.label}</span>
              </span>
              <div className="stage-bar">
                <div className={`stage-fill ${s.state}`} style={{ left: `${s.start}%`, width: `${s.end - s.start}%` }} />
              </div>
              <span className="mono muted" style={{ fontSize: "var(--t-12)", textAlign: "right" }}>{((s.end - s.start) * 0.02).toFixed(2)}s</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 12 }}>
        <div className="card" style={{ padding: 0 }}>
          <div className="row" style={{ padding: "10px 14px", borderBottom: "1px solid var(--hairline)", justifyContent: "space-between" }}>
            <div className="row gap-2"><h2 style={{ margin: 0, fontSize: "var(--t-13)", fontWeight: 600 }}>Event stream</h2>{playing && streamIdx < D.liveEvents.length && <span className="live" style={{ fontSize: 10 }}>streaming</span>}</div>
            <div className="row gap-2">
              <span className="chip">all</span>
              <span className="chip">errors</span>
              <button className="btn btn-sm">Export</button>
            </div>
          </div>
          <div style={{ maxHeight: 380, overflow: "auto", fontFamily: "var(--font-mono)", fontSize: "var(--t-12)" }}>
            {events.map((e, i) => {
              const color = e.lvl === "ok" ? "var(--ok)" : e.lvl === "warn" ? "var(--warn)" : e.lvl === "err" ? "var(--danger)" : "var(--fg-muted)";
              return (
                <div key={i} className="row gap-3 stream-in" style={{ padding: "5px 14px", borderBottom: "1px solid var(--hairline)", lineHeight: 1.5 }}>
                  <span className="faint" style={{ width: 80 }}>{e.t}</span>
                  <span style={{ width: 38, color, fontWeight: 600, textTransform: "uppercase", fontSize: 10.5 }}>{e.lvl}</span>
                  <span style={{ flex: 1, color: "var(--fg)" }}>{e.msg}</span>
                </div>
              );
            })}
            {playing && streamIdx < D.liveEvents.length && (
              <div className="row gap-2" style={{ padding: "8px 14px", color: "var(--cyan)" }}>
                <span className="pulse" style={{ width: 6, height: 6, borderRadius: 999, background: "var(--cyan)" }} />
                <span>waiting for next event…</span>
              </div>
            )}
          </div>
        </div>

        <div className="col gap-3">
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section"><h2>Outputs</h2></div>
            <div className="col gap-2">
              <div className="row gap-3" style={{ padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                <Icon name="repairs" s={14} style={{ color: "var(--ok)" }} />
                <div className="col grow"><span className="mono" style={{ fontSize: "var(--t-13)" }}>PR-2210</span><span className="faint" style={{ fontSize: "var(--t-12)" }}>opened · awaiting approval</span></div>
                <button className="btn btn-sm" onClick={() => onNav("repair", "PR-2210")}>Open →</button>
              </div>
              <div className="row gap-3" style={{ padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                <Icon name="findings" s={14} style={{ color: "var(--warn)" }} />
                <div className="col grow"><span style={{ fontSize: "var(--t-13)" }}>1 finding · F-9001</span><span className="faint" style={{ fontSize: "var(--t-12)" }}>missing-pyproject</span></div>
              </div>
              <div className="row gap-3" style={{ padding: "8px 0" }}>
                <Icon name="audit" s={14} style={{ color: "var(--info)" }} />
                <div className="col grow"><span style={{ fontSize: "var(--t-13)" }}>Audit entry A-44912</span><span className="faint" style={{ fontSize: "var(--t-12)" }}>policy:auto-fix:pyproject</span></div>
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div className="h-section"><h2>Sandbox</h2></div>
            <div className="row gap-3" style={{ marginTop: 4, fontSize: "var(--t-13)" }}>
              <Icon name="shield" s={14} style={{ color: "var(--ok)" }} />
              <div className="col grow">
                <span className="mono">matrixlab-py311</span>
                <span className="faint" style={{ fontSize: "var(--t-12)" }}>image · sha256:9a71…b3 · ttl 6m</span>
              </div>
              <Pill tone="ok" dot>verified</Pill>
            </div>
            <div className="row gap-3" style={{ marginTop: 10, fontSize: "var(--t-12)" }}>
              <span className="muted">CPU 14% · MEM 42MB · NET egress denied</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
