import React from "react";

import { HealthBar, Icon, RepoIcon } from "../components/atoms.jsx";
import { useRepos } from "../hooks/useRepos.js";
import { useCreateSchedule } from "../hooks/useSchedules.js";

const POLICIES = [
  { id: "conservative", label: "Conservative", desc: "auto-fix only · human approval · no auto-merge", tone: "ok", icon: "shield" },
  { id: "balanced", label: "Balanced", desc: "auto-fix + LLM-assist · human approval", tone: "info", icon: "spark" },
  { id: "aggressive", label: "Aggressive", desc: "all strategies · auto-merge if green", tone: "warn", icon: "play" },
];

const SCHEDULES = [
  { id: "on-push", label: "On push", cron: "*/15 * * * *", note: "Effectively every 15 minutes until webhook triggers ship" },
  { id: "hourly", label: "Hourly", cron: "0 * * * *" },
  { id: "daily", label: "Daily 02:00 UTC", cron: "0 2 * * *" },
  { id: "manual", label: "Manual only", cron: "0 0 31 2 *", note: "Effectively never; toggled off" },
];

export const AutoRepairModal = ({ open, onClose, onLaunch }) => {
  const reposQuery = useRepos({ limit: 200 });
  const createSchedule = useCreateSchedule();
  const items = reposQuery.data?.items || [];

  const [selected, setSelected] = React.useState(new Set());
  const [policy, setPolicy] = React.useState("conservative");
  const [scheduleId, setScheduleId] = React.useState("on-push");
  const [name, setName] = React.useState("Auto-repair");
  const [search, setSearch] = React.useState("");
  const [submitError, setSubmitError] = React.useState(null);

  React.useEffect(() => {
    if (open) {
      setSelected(new Set());
      setSubmitError(null);
    }
  }, [open]);

  if (!open) return null;
  const filtered = items.filter(
    (r) => !search || r.full_name?.toLowerCase().includes(search.toLowerCase()),
  );
  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((r) => r.id)));
  };

  const submit = async () => {
    setSubmitError(null);
    if (selected.size === 0) {
      setSubmitError("Select at least one repo.");
      return;
    }
    const sched = SCHEDULES.find((s) => s.id === scheduleId);
    try {
      await createSchedule.mutateAsync({
        name,
        cron: sched.cron,
        timezone: "UTC",
        repo_ids: Array.from(selected),
        policy,
        trigger_label: scheduleId,
        enabled: scheduleId !== "manual",
      });
      onLaunch?.({
        repos: Array.from(selected),
        policy,
        schedule: scheduleId,
      });
      onClose();
    } catch (err) {
      setSubmitError(err?.detail || err?.message || "Failed to enable auto-repair");
    }
  };

  return (
    <div className="cmd-overlay" onClick={onClose} style={{ paddingTop: "8vh" }}>
      <div
        className="run-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ width: 720 }}
      >
        <div className="run-head">
          <div className="row gap-3">
            <span
              style={{
                width: 28,
                height: 28,
                borderRadius: 7,
                background: "var(--grad-brand)",
                display: "grid",
                placeItems: "center",
                boxShadow: "0 4px 12px rgba(139,92,246,0.25)",
              }}
            >
              <Icon name="repairs" s={14} style={{ color: "white" }} />
            </span>
            <div className="col">
              <h2 style={{ margin: 0, fontSize: "var(--t-16)", fontWeight: 600 }}>
                Auto-repair mode
              </h2>
              <span className="muted" style={{ fontSize: "var(--t-12)" }}>
                Continuously runs repair on selected repos under a policy
              </span>
            </div>
          </div>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>
            ✕
          </button>
        </div>

        <div
          style={{
            padding: "14px 18px",
            borderBottom: "1px solid var(--hairline)",
          }}
        >
          <div
            className="muted"
            style={{
              fontSize: "var(--t-12)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: 8,
            }}
          >
            Schedule name
          </div>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: "100%", marginBottom: 12 }}
          />

          <div
            className="muted"
            style={{
              fontSize: "var(--t-12)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: 8,
            }}
          >
            Policy
          </div>
          <div className="strategy-grid">
            {POLICIES.map((p) => (
              <div
                key={p.id}
                className={`strategy-card ${policy === p.id ? "is-active" : ""}`}
                onClick={() => setPolicy(p.id)}
              >
                <span
                  className="strategy-ico"
                  style={{
                    background: `var(--${p.tone}-bg)`,
                    color: `var(--${p.tone})`,
                    borderColor: `var(--${p.tone}-border)`,
                  }}
                >
                  <Icon name={p.icon} s={14} />
                </span>
                <div className="col grow">
                  <span style={{ fontSize: "var(--t-13)", fontWeight: 600 }}>
                    {p.label}
                  </span>
                  <span className="faint" style={{ fontSize: "var(--t-12)" }}>
                    {p.desc}
                  </span>
                </div>
                <span className={`radio ${policy === p.id ? "is-on" : ""}`} />
              </div>
            ))}
          </div>

          <div className="row gap-2" style={{ marginTop: 14 }}>
            <span className="muted" style={{ fontSize: "var(--t-12)" }}>
              Schedule:
            </span>
            {SCHEDULES.map((s) => (
              <span
                key={s.id}
                className={`chip ${scheduleId === s.id ? "is-active" : ""}`}
                onClick={() => setScheduleId(s.id)}
                title={s.note || s.cron}
              >
                {s.label}
              </span>
            ))}
          </div>
        </div>

        <div
          style={{
            padding: "12px 18px",
            borderBottom: "1px solid var(--hairline)",
          }}
        >
          <div
            className="row"
            style={{ justifyContent: "space-between", marginBottom: 8 }}
          >
            <div
              className="muted"
              style={{
                fontSize: "var(--t-12)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              Selected repos · {selected.size} of {filtered.length}
            </div>
            <a
              className="muted"
              style={{
                cursor: "pointer",
                color: "var(--cyan)",
                fontSize: "var(--t-12)",
              }}
              onClick={toggleAll}
            >
              {selected.size === filtered.length ? "Deselect all" : "Select all"}
            </a>
          </div>
          <div style={{ position: "relative", marginBottom: 8 }}>
            <Icon
              name="search"
              s={12}
              style={{
                position: "absolute",
                left: 9,
                top: 8,
                color: "var(--fg-faint)",
              }}
            />
            <input
              className="input"
              placeholder="Filter repos…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: "100%", paddingLeft: 26 }}
            />
          </div>
          <div
            style={{
              maxHeight: 220,
              overflowY: "auto",
              border: "1px solid var(--hairline)",
              borderRadius: 6,
            }}
          >
            {reposQuery.isLoading && (
              <div className="muted" style={{ padding: 10 }}>Loading repos…</div>
            )}
            {filtered.map((r) => (
              <label
                key={r.id}
                className="row gap-3 repo-pick-row"
                style={{
                  padding: "8px 12px",
                  borderBottom: "1px solid var(--hairline)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(r.id)}
                  onChange={() => toggle(r.id)}
                />
                <RepoIcon platform={r.provider} s={12} />
                <span style={{ flex: 1, fontSize: "var(--t-13)" }}>
                  {r.full_name}
                </span>
                <HealthBar value={r.health_score} />
                <span
                  className="faint mono"
                  style={{ fontSize: "var(--t-12)", width: 60, textAlign: "right" }}
                >
                  {r.open_findings} find
                </span>
              </label>
            ))}
            {filtered.length === 0 && !reposQuery.isLoading && (
              <div className="muted" style={{ padding: 10 }}>
                No repos match this filter.
              </div>
            )}
          </div>
        </div>

        {submitError && (
          <div
            role="alert"
            style={{
              margin: "10px 18px 0",
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

        <div className="run-foot">
          <span className="muted" style={{ fontSize: "var(--t-12)" }}>
            <b>{selected.size}</b> repos · cron{" "}
            <b className="mono">
              {SCHEDULES.find((s) => s.id === scheduleId)?.cron}
            </b>{" "}
            · policy <b>{policy}</b>
          </span>
          <div className="row gap-2">
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={submit}
              disabled={createSchedule.isPending}
            >
              <Icon name="play" s={12} />
              {createSchedule.isPending
                ? " Enabling…"
                : " Enable auto-repair"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
