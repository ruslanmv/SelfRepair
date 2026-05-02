import React from "react";

import { Icon, Pill } from "../components/atoms.jsx";

const AUDIT_ENTRIES = [
  { t: "12:42:08.012Z", actor: "system:webhook", action: "job.create", target: "J-77821", outcome: "ok", hash: "0a7f…91", det: { trigger: "push", ref: "refs/heads/master", commit: "a8f12c4" } },
  { t: "12:42:08.044Z", actor: "policy.opa",     action: "policy.eval", target: "auto-fix:pyproject", outcome: "ALLOW", hash: "44b1…c2", det: { rule: "allow.auto_fix.pyproject", paths: "pyproject.toml" } },
  { t: "12:42:08.213Z", actor: "agent:layout",   action: "discover", target: "ruslanmv/SelfRepair", outcome: "ok", hash: "9c11…ff", det: { files: 84, langs: ["py", "yaml", "md"] } },
  { t: "12:42:08.583Z", actor: "agent:standards", action: "finding.open", target: "F-9001", outcome: "warn", hash: "a8f1…e0", det: { kind: "missing-pyproject:tool.uv", severity: "high" } },
  { t: "12:42:08.611Z", actor: "agent:health",   action: "finding.open", target: "F-9006", outcome: "warn", hash: "2c84…b9", det: { kind: "missing-health-test", severity: "low" } },
  { t: "12:42:08.795Z", actor: "agent:planner",  action: "strategy.pick", target: "auto-fix:pyproject", outcome: "ok", hash: "73d2…04", det: { confidence: 0.94 } },
  { t: "12:42:09.041Z", actor: "sandbox:matrixlab-py311", action: "container.start", target: "sha256:9a71b3", outcome: "ok", hash: "5e0a…8c", det: { egress: "denied", ttl: "6m" } },
  { t: "12:42:09.711Z", actor: "sandbox",        action: "test.run", target: "pytest tests/test_health.py", outcome: "ok", hash: "8a44…11", det: { passed: 1, failed: 0, duration: "0.04s" } },
  { t: "12:42:09.882Z", actor: "cosign",         action: "artifact.sign", target: "PR-2210/diff", outcome: "ok", hash: "rekor:84112", det: { cert: "Fulcio", oidc: "github" } },
  { t: "12:42:10.041Z", actor: "agent:committer", action: "git.push", target: "selfrepair/auto-fix/pyproject-uv", outcome: "ok", hash: "git:7c1ab9", det: {} },
  { t: "12:42:10.082Z", actor: "agent:committer", action: "pr.open", target: "PR-2210", outcome: "ok", hash: "gh:2210", det: { state: "awaiting-approval" } },
];

export const AuditLogDrawer = ({ open, onClose, scope = "job", scopeId = "J-77821" }) => {
  const [filter, setFilter] = React.useState("all");
  const [expandedIdx, setExpandedIdx] = React.useState(2);
  const [verifying, setVerifying] = React.useState(false);

  if (!open) return null;
  const filtered = AUDIT_ENTRIES.filter((e) =>
    filter === "all" ? true : e.outcome === filter || e.outcome.toLowerCase().includes(filter),
  );

  const verifyChain = () => {
    setVerifying(true);
    setTimeout(() => setVerifying(false), 1200);
  };

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div className="col">
            <div className="row gap-2">
              <Icon name="audit" s={16} />
              <h2 style={{ margin: 0, fontSize: "var(--t-16)", fontWeight: 600 }}>Audit log</h2>
              <Pill tone="ok" dot>tamper-evident</Pill>
            </div>
            <span className="muted mono" style={{ fontSize: "var(--t-12)", marginTop: 2 }}>scope: {scope} · {scopeId} · {AUDIT_ENTRIES.length} entries</span>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><Icon name="caret" s={14} style={{ transform: "rotate(180deg)" }} /></button>
        </div>

        <div className="drawer-trust">
          <div className="trust-cell">
            <span className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.05em" }}>Hash chain</span>
            <span className="row gap-2" style={{ marginTop: 2 }}>
              <Icon name="check" s={12} style={{ color: "var(--ok)" }} />
              <span className="mono" style={{ fontSize: "var(--t-12)" }}>continuous · {AUDIT_ENTRIES.length}/{AUDIT_ENTRIES.length}</span>
            </span>
          </div>
          <div className="trust-cell">
            <span className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.05em" }}>Sigstore</span>
            <span className="row gap-2" style={{ marginTop: 2 }}>
              <Icon name="check" s={12} style={{ color: "var(--ok)" }} />
              <span className="mono" style={{ fontSize: "var(--t-12)" }}>rekor #84112</span>
            </span>
          </div>
          <div className="trust-cell">
            <span className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.05em" }}>SLSA</span>
            <span className="row gap-2" style={{ marginTop: 2 }}>
              <Icon name="shield" s={12} style={{ color: "var(--ok)" }} />
              <span className="mono" style={{ fontSize: "var(--t-12)" }}>level 3</span>
            </span>
          </div>
          <button className="btn btn-sm" onClick={verifyChain}>
            {verifying ? (
              <>
                <span className="pulse" style={{ width: 6, height: 6, borderRadius: 999, background: "var(--cyan)" }} /> Verifying…
              </>
            ) : (
              <>
                <Icon name="retry" s={12} /> Verify chain
              </>
            )}
          </button>
        </div>

        <div className="row gap-2" style={{ padding: "10px 16px", borderBottom: "1px solid var(--hairline)" }}>
          {["all", "ok", "warn", "ALLOW", "DENY"].map((f) => (
            <span key={f} className={`chip ${filter === f ? "is-active" : ""}`} onClick={() => setFilter(f)}>{f}</span>
          ))}
          <span className="grow" />
          <button className="btn btn-sm"><Icon name="external" s={11} /> Export JSONL</button>
        </div>

        <div className="drawer-body">
          {filtered.map((e, i) => {
            const expanded = i === expandedIdx;
            const tone = e.outcome === "ok" || e.outcome === "ALLOW"
              ? "ok"
              : e.outcome === "warn"
                ? "warn"
                : e.outcome === "DENY"
                  ? "danger"
                  : "info";
            return (
              <div key={i} className={`audit-row ${expanded ? "is-expanded" : ""}`} onClick={() => setExpandedIdx(expanded ? -1 : i)}>
                <div className="audit-rail" style={{ background: `var(--${tone})` }} />
                <div className="col grow" style={{ minWidth: 0 }}>
                  <div className="row gap-2">
                    <span className="mono faint" style={{ fontSize: 10.5, width: 110 }}>{e.t}</span>
                    <Pill tone={tone} dot>{e.outcome}</Pill>
                    <span className="mono" style={{ fontSize: "var(--t-12)", fontWeight: 600 }}>{e.action}</span>
                    <span className="muted truncate" style={{ fontSize: "var(--t-12)" }}>{e.target}</span>
                    <span className="grow" />
                    <span className="sha mono">{e.hash}</span>
                    <Icon name="caret" s={11} style={{ color: "var(--fg-faint)", transform: expanded ? "rotate(90deg)" : "none", transition: "transform 0.15s" }} />
                  </div>
                  <div className="row gap-2" style={{ marginTop: 3, fontSize: "var(--t-12)" }}>
                    <span className="muted">by</span>
                    <span className="mono">{e.actor}</span>
                  </div>
                  {expanded && (
                    <div className="audit-detail">
                      <pre className="code" style={{ margin: "10px 0 0", fontSize: 11 }}>{JSON.stringify(e.det, null, 2)}</pre>
                      <div className="row gap-2" style={{ marginTop: 8 }}>
                        <button className="btn btn-sm">Copy hash</button>
                        <button className="btn btn-sm">View on Rekor</button>
                        <span className="grow" />
                        <button className="btn btn-sm">Replay step</button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
};
