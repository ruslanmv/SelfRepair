import React from "react";

import { Icon } from "../components/atoms.jsx";

const REPAIR_STEPS = [
  { id: "select", label: "Select target", icon: "repos", desc: "Repo & policy scope" },
  { id: "policy", label: "Policy gate", icon: "shield", desc: "OPA dry-run · ALLOW/DENY" },
  { id: "discover", label: "Discover", icon: "search", desc: "Layout · standards · health probes" },
  { id: "analyze", label: "Analyze", icon: "findings", desc: "Detect findings · fingerprint" },
  { id: "plan", label: "Plan strategy", icon: "spark", desc: "auto-fix · llm-assist (signed)" },
  { id: "sandbox", label: "Sandbox", icon: "shield", desc: "Hermetic image · uv sync · pytest" },
  { id: "sign", label: "Sign & attest", icon: "check", desc: "Sigstore · Rekor · SLSA-3" },
  { id: "open", label: "Open repair PR", icon: "branch", desc: "Awaiting human approval" },
];

const RUN_LOG = [
  { t: "+0.00s", lvl: "info", step: 0, msg: "user.invoke run-repair · target=ruslanmv/SelfRepair · branch=master" },
  { t: "+0.04s", lvl: "ok",   step: 1, msg: "policy.eval bundle=selfrepair/v3 · decision=ALLOW · matched=auto-fix:pyproject" },
  { t: "+0.21s", lvl: "info", step: 2, msg: "discover.layout files=84 · python=37 · yaml=6 · md=8" },
  { t: "+0.34s", lvl: "info", step: 2, msg: "discover.standards Makefile=ok · pyproject=warn · tests=ok" },
  { t: "+0.58s", lvl: "warn", step: 3, msg: "analyze.finding F-9001 missing-pyproject:tool.uv  fp=a8f1…" },
  { t: "+0.61s", lvl: "warn", step: 3, msg: "analyze.finding F-9006 missing-health-test         fp=2c84…" },
  { t: "+0.79s", lvl: "info", step: 4, msg: "plan.strategy auto-fix:pyproject (template) · confidence=0.94" },
  { t: "+0.83s", lvl: "info", step: 4, msg: "plan.strategy auto-fix:health_test (template) · confidence=0.99" },
  { t: "+1.04s", lvl: "info", step: 5, msg: "sandbox.start image=matrixlab-py311 sha256:9a71b3… · egress=denied" },
  { t: "+1.42s", lvl: "info", step: 5, msg: "sandbox.exec uv sync → resolved 47 pkgs in 612ms" },
  { t: "+1.71s", lvl: "ok",   step: 5, msg: "sandbox.exec pytest → 1 passed in 0.04s ✓" },
  { t: "+1.88s", lvl: "ok",   step: 6, msg: "sign.cosign cert=Fulcio · keyless OIDC=github · rekor.idx=84112" },
  { t: "+1.92s", lvl: "ok",   step: 6, msg: "attest.slsa level=3 · builder=selfrepair-agent v1.0.4" },
  { t: "+2.04s", lvl: "ok",   step: 7, msg: "git.push branch=selfrepair/auto-fix/pyproject-uv ✓" },
  { t: "+2.08s", lvl: "ok",   step: 7, msg: "pr.open PR-2210 ‘Add pyproject.toml [tool.uv] section’ → awaiting-approval" },
];

export const RunRepairModal = ({ open, onClose, onNav, defaultRepo }) => {
  const [active, setActive] = React.useState(0);
  const [logIdx, setLogIdx] = React.useState(0);
  const [done, setDone] = React.useState(false);
  const [paused, setPaused] = React.useState(false);
  const [target, setTarget] = React.useState(defaultRepo || "ruslanmv/SelfRepair");
  const [strategy, setStrategy] = React.useState("auto-fix-only");
  const [autoMerge, setAutoMerge] = React.useState(false);
  const [phase, setPhase] = React.useState("config"); // config -> run -> done
  const logEndRef = React.useRef(null);

  React.useEffect(() => {
    if (open) {
      setActive(0);
      setLogIdx(0);
      setDone(false);
      setPaused(false);
      setPhase("config");
      setTarget(defaultRepo || "ruslanmv/SelfRepair");
    }
  }, [open, defaultRepo]);

  React.useEffect(() => {
    if (phase !== "run" || paused) return;
    if (logIdx >= RUN_LOG.length) {
      setDone(true);
      setPhase("done");
      return;
    }
    const ev = RUN_LOG[logIdx];
    const t = setTimeout(() => {
      setLogIdx((i) => i + 1);
      setActive(ev.step);
    }, 280 + Math.random() * 260);
    return () => clearTimeout(t);
  }, [logIdx, phase, paused]);

  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "end" });
  }, [logIdx]);

  if (!open) return null;
  const visibleLog = RUN_LOG.slice(0, logIdx);

  return (
    <div className="cmd-overlay" onClick={onClose} style={{ paddingTop: "6vh" }}>
      <div className="run-modal" onClick={(e) => e.stopPropagation()}>
        <div className="run-head">
          <div className="row gap-3">
            <span className="run-pulse" data-state={done ? "done" : phase === "run" ? "run" : "idle"}>
              <span /><span /><span />
            </span>
            <div className="col">
              <h2 style={{ margin: 0, fontSize: "var(--t-16)", fontWeight: 600 }}>
                {phase === "config" ? "Run repair" : phase === "run" ? "Repair in progress…" : "Repair complete"}
              </h2>
              <span className="muted mono" style={{ fontSize: "var(--t-12)" }}>{target} · job J-{77821 + (logIdx % 3)}</span>
            </div>
          </div>
          <div className="row gap-2">
            {phase === "run" && (
              <button className="btn btn-sm" onClick={() => setPaused((p) => !p)}>
                <Icon name={paused ? "play" : "pause"} s={12} />
                {paused ? "Resume" : "Pause"}
              </button>
            )}
            <button className="btn btn-sm btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>

        {phase === "config" && (
          <div style={{ padding: 18 }}>
            <div className="muted" style={{ fontSize: "var(--t-12)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Target</div>
            <input className="input" value={target} onChange={(e) => setTarget(e.target.value)} style={{ width: "100%", marginBottom: 14 }} />

            <div className="muted" style={{ fontSize: "var(--t-12)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Strategy</div>
            <div className="strategy-grid">
              {[
                { id: "auto-fix-only", label: "Auto-fix only", desc: "Templates only. Deterministic. No LLM.", tone: "ok", icon: "check" },
                { id: "auto-fix-llm",  label: "Auto-fix + LLM-assist", desc: "Falls back to OllaBridge for unknown patterns.", tone: "info", icon: "spark" },
                { id: "discover-only", label: "Discover only", desc: "Scan + report findings. Don't open PRs.", tone: "muted", icon: "search" },
              ].map((s) => (
                <div key={s.id} className={`strategy-card ${strategy === s.id ? "is-active" : ""}`} onClick={() => setStrategy(s.id)}>
                  <span className="strategy-ico" style={{ background: `var(--${s.tone}-bg)`, color: `var(--${s.tone === "muted" ? "fg-muted" : s.tone})`, borderColor: `var(--${s.tone === "muted" ? "neutral" : s.tone}-border)` }}>
                    <Icon name={s.icon} s={14} />
                  </span>
                  <div className="col grow"><span style={{ fontSize: "var(--t-13)", fontWeight: 600 }}>{s.label}</span><span className="faint" style={{ fontSize: "var(--t-12)" }}>{s.desc}</span></div>
                  <span className={`radio ${strategy === s.id ? "is-on" : ""}`} />
                </div>
              ))}
            </div>

            <div className="hairline-t" style={{ marginTop: 14, paddingTop: 12 }}>
              <label className="row gap-2" style={{ fontSize: "var(--t-13)", cursor: "pointer" }}>
                <input type="checkbox" checked={autoMerge} onChange={(e) => setAutoMerge(e.target.checked)} />
                <span>Auto-merge if all gates pass <span className="faint">(requires policy: allow:auto-merge)</span></span>
              </label>
            </div>

            <div className="row gap-2" style={{ marginTop: 18, justifyContent: "flex-end" }}>
              <button className="btn" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" onClick={() => setPhase("run")}><Icon name="play" s={12} /> Run repair</button>
            </div>
          </div>
        )}

        {phase !== "config" && (
          <>
            <div className="step-rail">
              {REPAIR_STEPS.map((s, i) => {
                const state = i < active ? "done" : i === active ? (done ? "done" : "active") : "idle";
                return (
                  <React.Fragment key={s.id}>
                    <div className={`step-node state-${state}`}>
                      <span className="step-ico"><Icon name={state === "done" ? "check" : s.icon} s={13} /></span>
                      <div className="col">
                        <span style={{ fontSize: "var(--t-12)", fontWeight: 600 }}>{s.label}</span>
                        <span className="faint" style={{ fontSize: 10.5 }}>{s.desc}</span>
                      </div>
                    </div>
                    {i < REPAIR_STEPS.length - 1 && <span className={`step-line state-${i < active ? "done" : "idle"}`} />}
                  </React.Fragment>
                );
              })}
            </div>

            <div className="run-log">
              {visibleLog.map((e, i) => {
                const color = e.lvl === "ok" ? "var(--ok)" : e.lvl === "warn" ? "var(--warn)" : e.lvl === "err" ? "var(--danger)" : "var(--cyan)";
                return (
                  <div key={i} className="run-log-row stream-in">
                    <span className="faint mono" style={{ width: 60 }}>{e.t}</span>
                    <span className="mono" style={{ width: 38, color, fontWeight: 700, textTransform: "uppercase", fontSize: 10 }}>{e.lvl}</span>
                    <span className="mono" style={{ flex: 1 }}>{e.msg}</span>
                  </div>
                );
              })}
              {!done && phase === "run" && !paused && (
                <div className="run-log-row" style={{ color: "var(--cyan)" }}>
                  <span className="pulse mono" style={{ width: 60 }}>···</span>
                  <span className="mono">streaming next event…</span>
                </div>
              )}
              <div ref={logEndRef} />
            </div>

            <div className="run-foot">
              <div className="row gap-3 grow muted" style={{ fontSize: "var(--t-12)" }}>
                <span><Icon name="shield" s={11} style={{ verticalAlign: "-2px" }} /> hermetic sandbox</span>
                <span>·</span>
                <span><Icon name="check" s={11} style={{ verticalAlign: "-2px" }} /> sigstore signed</span>
                <span>·</span>
                <span>SLSA-3 attested</span>
              </div>
              {done && (
                <div className="row gap-2">
                  <button className="btn" onClick={() => { onClose(); onNav("job", "J-77821"); }}>Open job</button>
                  <button className="btn btn-primary" onClick={() => { onClose(); onNav("repair", "PR-2210"); }}>Review PR-2210 →</button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
