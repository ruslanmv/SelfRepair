import React from "react";

import { Icon, Pill, RepoIcon } from "../components/atoms.jsx";
import { useRepos } from "../hooks/useRepos.js";
import {
  useCreateRoutine,
  useDeleteRoutine,
  usePatchRoutine,
  useRoutineCapabilities,
  useRoutines,
  useSetRoutineMergeLock,
} from "../hooks/useRoutines.js";

const DAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

const KINDS = [
  {
    id: "health_repair",
    title: "Health + AutoRepair",
    short: "Health",
    icon: "repairs",
    tone: "info",
    description:
      "Analyze the selected branch, detect delivery errors, validate repairs, and prepare a repair PR back to that branch.",
  },
  {
    id: "pr_review",
    title: "Merge Request Review",
    short: "Review",
    icon: "audit",
    tone: "warn",
    description:
      "Inspect open PR/MR commits and diffs targeting the branch, then record actionable review findings.",
  },
  {
    id: "review_remediation",
    title: "Review Remediation",
    short: "Fix reviews",
    icon: "spark",
    tone: "info",
    description:
      "Read unresolved review findings, prepare minimal fixes on the PR head branch, validate, and request review again.",
  },
  {
    id: "promotion",
    title: "Promotion Gate",
    short: "Promote",
    icon: "shield",
    tone: "ok",
    description:
      "Promote a healthy development branch only after checks and review threads are resolved.",
  },
];

const kindMeta = (kind) => KINDS.find((item) => item.id === kind) || KINDS[0];
const protectedBranch = (branch) => ["main", "master"].includes((branch || "").toLowerCase());

function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function defaultDraft(kind = "health_repair", repo = null) {
  const promotion = kind === "promotion";
  const source = repo?.default_branch || "develop";
  return {
    repo_id: repo?.id || "",
    name:
      kind === "health_repair"
        ? "Daily development health"
        : kind === "pr_review"
          ? "Daily merge request review"
          : kind === "review_remediation"
            ? "Resolve review findings"
            : "Promote development",
    kind,
    enabled: true,
    timezone: browserTimezone(),
    schedule_time:
      kind === "health_repair"
        ? "07:00"
        : kind === "pr_review"
          ? "11:00"
          : kind === "review_remediation"
            ? "15:00"
            : "18:00",
    schedule_days: [0, 1, 2, 3, 4],
    source_branch: source,
    target_branch: promotion ? "master" : source,
    depends_on_routine_id: null,
    execution_mode: "human_review",
    requirements: {
      checks_green: true,
      reviews_resolved: true,
      codeowners_approval: true,
    },
    config: {},
  };
}

function scheduleLabel(routine) {
  const days = routine.schedule_days || [];
  const dayText =
    days.length === 7
      ? "Every day"
      : days.join(",") === "0,1,2,3,4"
        ? "Weekdays"
        : days.map((day) => DAY_LABELS[day]).join(" ");
  return `${dayText} · ${routine.schedule_time} · ${routine.timezone}`;
}

function RoutineEditor({ open, routine, repos, routines, initialKind, onClose, onSave, pending }) {
  const initialRepo = repos[0] || null;
  const [draft, setDraft] = React.useState(defaultDraft(initialKind, initialRepo));
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!open) return;
    setError("");
    if (routine) {
      setDraft({
        repo_id: routine.repo_id,
        name: routine.name,
        kind: routine.kind,
        enabled: routine.enabled,
        timezone: routine.timezone,
        schedule_time: routine.schedule_time,
        schedule_days: routine.schedule_days || [0, 1, 2, 3, 4],
        source_branch: routine.source_branch,
        target_branch: routine.target_branch || routine.source_branch,
        depends_on_routine_id: routine.depends_on_routine_id || null,
        execution_mode: routine.execution_mode,
        requirements: routine.requirements || {
          checks_green: true,
          reviews_resolved: true,
          codeowners_approval: true,
        },
        config: routine.config || {},
      });
    } else {
      setDraft(defaultDraft(initialKind, repos[0] || null));
    }
  }, [open, routine, initialKind, repos]);

  if (!open) return null;

  const update = (field, value) => setDraft((prev) => ({ ...prev, [field]: value }));
  const toggleDay = (day) => {
    const current = new Set(draft.schedule_days);
    if (current.has(day)) current.delete(day);
    else current.add(day);
    const next = Array.from(current).sort((a, b) => a - b);
    if (next.length) update("schedule_days", next);
  };

  const submit = async () => {
    if (!draft.repo_id) {
      setError("Select a repository.");
      return;
    }
    if (!draft.name.trim() || !draft.source_branch.trim()) {
      setError("Name and source branch are required.");
      return;
    }
    try {
      await onSave(draft);
    } catch (err) {
      setError(err?.detail || err?.message || "Could not save routine");
    }
  };

  const targetIsProtected = protectedBranch(draft.target_branch);

  return (
    <div className="cmd-overlay" onClick={onClose} style={{ paddingTop: "5vh" }}>
      <div
        className="run-modal"
        onClick={(event) => event.stopPropagation()}
        style={{ width: 780, maxHeight: "90vh", overflowY: "auto" }}
      >
        <div className="run-head">
          <div className="row gap-3">
            <span
              style={{
                width: 30,
                height: 30,
                borderRadius: 7,
                background: "var(--grad-brand)",
                display: "grid",
                placeItems: "center",
              }}
            >
              <Icon name="jobs" s={15} style={{ color: "white" }} />
            </span>
            <div className="col">
              <h2 style={{ margin: 0, fontSize: "var(--t-16)", fontWeight: 600 }}>
                {routine ? "Edit routine" : "New routine"}
              </h2>
              <span className="muted" style={{ fontSize: "var(--t-12)" }}>
                Configure when SelfRepair should inspect, repair, review, or promote a branch.
              </span>
            </div>
          </div>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: "16px 18px" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
              marginBottom: 16,
            }}
          >
            <label className="col gap-2">
              <span className="muted" style={{ fontSize: "var(--t-12)" }}>Routine name</span>
              <input
                className="input"
                value={draft.name}
                onChange={(event) => update("name", event.target.value)}
              />
            </label>
            <label className="col gap-2">
              <span className="muted" style={{ fontSize: "var(--t-12)" }}>Repository</span>
              <select
                className="input"
                value={draft.repo_id}
                disabled={Boolean(routine)}
                onChange={(event) => {
                  const repo = repos.find((item) => item.id === event.target.value);
                  setDraft((prev) => ({
                    ...prev,
                    repo_id: event.target.value,
                    source_branch: repo?.default_branch || prev.source_branch,
                    target_branch:
                      prev.kind === "promotion"
                        ? prev.target_branch || "master"
                        : repo?.default_branch || prev.target_branch,
                  }));
                }}
              >
                <option value="">Select repo…</option>
                {repos.map((repo) => (
                  <option key={repo.id} value={repo.id}>{repo.full_name}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="muted" style={{ fontSize: "var(--t-12)", marginBottom: 8 }}>
            What should this routine do?
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: 8,
              marginBottom: 16,
            }}
          >
            {KINDS.map((item) => {
              const selected = draft.kind === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  className="card"
                  onClick={() => {
                    const next = { ...draft, kind: item.id };
                    if (item.id === "promotion" && !protectedBranch(next.target_branch)) {
                      next.target_branch = "master";
                    }
                    setDraft(next);
                  }}
                  style={{
                    padding: 12,
                    textAlign: "left",
                    cursor: "pointer",
                    borderColor: selected ? "var(--brand)" : "var(--hairline)",
                    background: selected ? "var(--bg-elev-2)" : undefined,
                  }}
                >
                  <div className="row gap-2" style={{ marginBottom: 5 }}>
                    <Icon name={item.icon} s={14} />
                    <b style={{ fontSize: "var(--t-13)" }}>{item.title}</b>
                    {selected && <Icon name="check" s={13} style={{ marginLeft: "auto" }} />}
                  </div>
                  <span className="muted" style={{ fontSize: "var(--t-12)" }}>
                    {item.description}
                  </span>
                </button>
              );
            })}
          </div>

          <div
            className="card"
            style={{ padding: 12, marginBottom: 16, background: "var(--bg-elev-1)" }}
          >
            <div className="row gap-2" style={{ marginBottom: 10 }}>
              <Icon name="branch" s={14} />
              <b style={{ fontSize: "var(--t-13)" }}>Branch flow</b>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 34px 1fr", gap: 8, alignItems: "end" }}>
              <label className="col gap-2">
                <span className="muted" style={{ fontSize: "var(--t-12)" }}>Source / analyzed branch</span>
                <input
                  className="input mono"
                  value={draft.source_branch}
                  placeholder="develop"
                  onChange={(event) => update("source_branch", event.target.value)}
                />
              </label>
              <div style={{ textAlign: "center", paddingBottom: 7 }}>→</div>
              <label className="col gap-2">
                <span className="muted" style={{ fontSize: "var(--t-12)" }}>PR / promotion target</span>
                <input
                  className="input mono"
                  value={draft.target_branch || ""}
                  placeholder={draft.kind === "promotion" ? "master" : "develop"}
                  onChange={(event) => update("target_branch", event.target.value)}
                />
              </label>
            </div>
            {targetIsProtected && (
              <div
                className="row gap-2"
                style={{
                  marginTop: 10,
                  padding: "8px 10px",
                  borderRadius: 6,
                  border: "1px solid var(--warn-border)",
                  background: "var(--warn-bg)",
                  fontSize: "var(--t-12)",
                }}
              >
                <Icon name="shield" s={13} style={{ color: "var(--warn)" }} />
                <span>
                  <b>{draft.target_branch}</b> is protected. Its merge lock will be ON by default.
                  Unlocking is a separate audited action after this routine is saved.
                </span>
              </div>
            )}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 14,
              marginBottom: 16,
            }}
          >
            <div className="card" style={{ padding: 12 }}>
              <b style={{ fontSize: "var(--t-13)" }}>Schedule</b>
              <div className="row gap-2" style={{ margin: "10px 0" }}>
                {DAY_LABELS.map((label, day) => (
                  <button
                    key={day}
                    type="button"
                    className={`chip ${draft.schedule_days.includes(day) ? "is-active" : ""}`}
                    onClick={() => toggleDay(day)}
                    style={{ minWidth: 30, justifyContent: "center" }}
                    title={["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day]}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "110px 1fr", gap: 8 }}>
                <input
                  className="input mono"
                  type="time"
                  value={draft.schedule_time}
                  onChange={(event) => update("schedule_time", event.target.value)}
                />
                <input
                  className="input"
                  value={draft.timezone}
                  onChange={(event) => update("timezone", event.target.value)}
                />
              </div>
            </div>

            <div className="card" style={{ padding: 12 }}>
              <b style={{ fontSize: "var(--t-13)" }}>Automation boundary</b>
              <div className="row gap-2" style={{ marginTop: 10 }}>
                {[
                  ["human_review", "Human review"],
                  ["automatic", "Automatic"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`chip ${draft.execution_mode === value ? "is-active" : ""}`}
                    onClick={() => update("execution_mode", value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="muted" style={{ fontSize: "var(--t-12)", lineHeight: 1.5, margin: "10px 0 0" }}>
                {draft.execution_mode === "human_review"
                  ? "Default: SelfRepair prepares the work and waits for a human at the merge gate."
                  : "Eligible steps may proceed automatically. main/master still cannot merge while its dedicated lock is enabled."}
              </p>
            </div>
          </div>

          <label className="col gap-2" style={{ marginBottom: 16 }}>
            <span className="muted" style={{ fontSize: "var(--t-12)" }}>
              Run after another routine (optional)
            </span>
            <select
              className="input"
              value={draft.depends_on_routine_id || ""}
              onChange={(event) => update("depends_on_routine_id", event.target.value || null)}
            >
              <option value="">No dependency</option>
              {routines
                .filter((item) => !routine || item.id !== routine.id)
                .map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
            </select>
          </label>

          <div className="card" style={{ padding: 12 }}>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
              <b style={{ fontSize: "var(--t-13)" }}>Merge requirements</b>
              <Pill tone="ok">all required</Pill>
            </div>
            {[
              ["checks_green", "Required checks are green"],
              ["reviews_resolved", "All review threads are resolved"],
              ["codeowners_approval", "CODEOWNERS approval is present"],
            ].map(([key, label]) => (
              <label key={key} className="row gap-2" style={{ padding: "5px 0", fontSize: "var(--t-13)" }}>
                <input
                  type="checkbox"
                  checked={Boolean(draft.requirements?.[key])}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      requirements: { ...prev.requirements, [key]: event.target.checked },
                    }))
                  }
                />
                {label}
              </label>
            ))}
          </div>

          {error && (
            <div
              role="alert"
              style={{
                marginTop: 12,
                padding: "8px 10px",
                borderRadius: 6,
                background: "var(--danger-bg)",
                color: "var(--danger)",
                fontSize: "var(--t-13)",
              }}
            >
              {error}
            </div>
          )}
        </div>

        <div className="run-foot">
          <span className="muted" style={{ fontSize: "var(--t-12)" }}>
            Routine definitions are audited. Recurring execution is a separate capability.
          </span>
          <div className="row gap-2">
            <button className="btn" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" onClick={submit} disabled={pending}>
              <Icon name="check" s={12} />
              {pending ? " Saving…" : " Save routine"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function RoutineCard({ routine, repo, routines, onEdit, onToggle, onDelete, onMergeLock, pending }) {
  const meta = kindMeta(routine.kind);
  const dependency = routines.find((item) => item.id === routine.depends_on_routine_id);
  const isProtected = protectedBranch(routine.target_branch);

  return (
    <div className="card" style={{ padding: 14 }}>
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        <span
          style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            display: "grid",
            placeItems: "center",
            background: `var(--${meta.tone}-bg)`,
            color: `var(--${meta.tone})`,
            border: `1px solid var(--${meta.tone}-border)`,
            flexShrink: 0,
          }}
        >
          <Icon name={meta.icon} s={16} />
        </span>
        <div className="col grow" style={{ minWidth: 0, gap: 5 }}>
          <div className="row gap-2" style={{ flexWrap: "wrap" }}>
            <b style={{ fontSize: "var(--t-14)" }}>{routine.name}</b>
            <Pill tone={routine.enabled ? "ok" : "neutral"}>{routine.enabled ? "ON" : "PAUSED"}</Pill>
            <Pill tone="neutral">{meta.short}</Pill>
            {isProtected && (
              <Pill tone={routine.merge_lock ? "warn" : "danger"}>
                {routine.merge_lock ? "merge locked" : "merge unlocked"}
              </Pill>
            )}
          </div>
          <div className="row gap-2 muted" style={{ fontSize: "var(--t-12)", flexWrap: "wrap" }}>
            {repo && (
              <>
                <RepoIcon platform={repo.provider} s={12} />
                <span>{repo.full_name}</span>
                <span>·</span>
              </>
            )}
            <span className="mono">{routine.source_branch}</span>
            <span>→</span>
            <span className="mono">{routine.target_branch}</span>
          </div>
          <div className="muted" style={{ fontSize: "var(--t-12)" }}>
            {scheduleLabel(routine)}
            {" · "}
            {routine.execution_mode === "automatic" ? "automatic" : "human review"}
            {dependency ? ` · after ${dependency.name}` : ""}
          </div>
        </div>
        <button
          className={`btn btn-sm ${routine.enabled ? "" : "btn-primary"}`}
          onClick={() => onToggle(routine)}
          disabled={pending}
        >
          <Icon name={routine.enabled ? "pause" : "play"} s={11} />
          {routine.enabled ? " Pause" : " Enable"}
        </button>
      </div>

      <div
        className="row"
        style={{
          justifyContent: "space-between",
          marginTop: 12,
          paddingTop: 10,
          borderTop: "1px solid var(--hairline)",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        <div className="row gap-2">
          <span className="faint" style={{ fontSize: "var(--t-12)" }}>
            Checks
          </span>
          {routine.requirements?.checks_green && <Pill tone="ok">CI green</Pill>}
          {routine.requirements?.reviews_resolved && <Pill tone="ok">reviews resolved</Pill>}
          {routine.requirements?.codeowners_approval && <Pill tone="ok">CODEOWNERS</Pill>}
        </div>
        <div className="row gap-2">
          {isProtected && (
            <button
              className="btn btn-sm"
              onClick={() => onMergeLock(routine)}
              disabled={pending}
              title={
                routine.merge_lock
                  ? "Requires an exact typed confirmation before SelfRepair can merge to this protected branch."
                  : "Re-lock this protected branch immediately."
              }
            >
              <Icon name="shield" s={11} />
              {routine.merge_lock ? " Unlock merge" : " Lock merge"}
            </button>
          )}
          <button className="btn btn-sm" onClick={() => onEdit(routine)}>Edit</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onDelete(routine)}>
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

export function Routines() {
  const routinesQuery = useRoutines({ limit: 200 });
  const capabilities = useRoutineCapabilities();
  const reposQuery = useRepos({ limit: 200 });
  const createRoutine = useCreateRoutine();
  const patchRoutine = usePatchRoutine();
  const deleteRoutine = useDeleteRoutine();
  const mergeLock = useSetRoutineMergeLock();

  const routines = routinesQuery.data?.items || [];
  const repos = reposQuery.data?.items || [];
  const [editorOpen, setEditorOpen] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  const [initialKind, setInitialKind] = React.useState("health_repair");

  const openNew = (kind = "health_repair") => {
    setEditing(null);
    setInitialKind(kind);
    setEditorOpen(true);
  };

  const save = async (draft) => {
    if (editing) {
      const { repo_id, ...body } = draft;
      await patchRoutine.mutateAsync({ id: editing.id, body });
    } else {
      await createRoutine.mutateAsync(draft);
    }
    setEditorOpen(false);
  };

  const toggle = async (routine) => {
    await patchRoutine.mutateAsync({
      id: routine.id,
      body: { enabled: !routine.enabled },
    });
  };

  const remove = async (routine) => {
    if (!window.confirm(`Remove routine "${routine.name}"? Its audit history is retained.`)) return;
    await deleteRoutine.mutateAsync(routine.id);
  };

  const changeMergeLock = async (routine) => {
    if (!routine.merge_lock) {
      if (!window.confirm(`Re-lock automatic merges to ${routine.target_branch}?`)) return;
      await mergeLock.mutateAsync({ id: routine.id, body: { locked: true } });
      return;
    }
    const expected = `UNLOCK ${routine.target_branch}`;
    const confirmation = window.prompt(
      `Protected branch safety lock\n\nThis allows an AUTOMATIC routine to merge into ${routine.target_branch} after all configured checks and reviews pass.\n\nType exactly: ${expected}`,
      "",
    );
    if (confirmation !== expected) return;
    await mergeLock.mutateAsync({
      id: routine.id,
      body: { locked: false, confirmation },
    });
  };

  const active = routines.filter((item) => item.enabled).length;
  const locked = routines.filter(
    (item) => protectedBranch(item.target_branch) && item.merge_lock,
  ).length;
  const definitionOnly = capabilities.data?.execution !== "enabled";
  const pending =
    createRoutine.isPending ||
    patchRoutine.isPending ||
    deleteRoutine.isPending ||
    mergeLock.isPending;

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16 }}
      >
        <div>
          <div className="row gap-2" style={{ marginBottom: 5 }}>
            <span className="live">automation · governed</span>
            <Pill tone={definitionOnly ? "warn" : "ok"}>
              {definitionOnly ? "executor not enabled" : "executor enabled"}
            </Pill>
          </div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
            Routines
          </h1>
          <p className="muted" style={{ margin: "3px 0 0", fontSize: "var(--t-13)" }}>
            Branch-aware health checks, repair loops, PR reviews, review remediation, and controlled promotion.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => openNew()}>
          <Icon name="plus" s={12} /> New routine
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 10,
          marginBottom: 14,
        }}
      >
        {[
          ["Active routines", active, "jobs"],
          ["Saved definitions", routines.length, "audit"],
          ["Protected locks ON", locked, "shield"],
        ].map(([label, value, icon]) => (
          <div key={label} className="card" style={{ padding: 12 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="muted" style={{ fontSize: "var(--t-12)" }}>{label}</span>
              <Icon name={icon} s={13} style={{ color: "var(--fg-faint)" }} />
            </div>
            <div style={{ fontSize: "var(--t-24)", fontWeight: 600, marginTop: 4 }}>{value}</div>
          </div>
        ))}
      </div>

      <div
        className="card"
        style={{
          padding: 14,
          marginBottom: 16,
          borderColor: "var(--warn-border)",
          background: "var(--warn-bg)",
        }}
      >
        <div className="row gap-3" style={{ alignItems: "flex-start" }}>
          <Icon name="shield" s={18} style={{ color: "var(--warn)", marginTop: 1 }} />
          <div className="col gap-1">
            <b style={{ fontSize: "var(--t-13)" }}>main/master cannot be silently merged by AI</b>
            <span className="muted" style={{ fontSize: "var(--t-12)", lineHeight: 1.5 }}>
              Promotion routines targeting a protected branch start locked. Unlocking uses a dedicated
              audited control with an exact typed confirmation. Even unlocked automatic promotion is
              still gated by green checks and zero unresolved review threads.
            </span>
          </div>
        </div>
      </div>

      <div className="h-section" style={{ marginBottom: 8 }}>
        <h2>End-to-end repair loop</h2>
        <span className="faint" style={{ fontSize: "var(--t-12)" }}>
          compose these independently or chain them with dependencies
        </span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 9,
          marginBottom: 20,
        }}
      >
        {KINDS.map((item, index) => (
          <div key={item.id} className="card" style={{ padding: 12, position: "relative" }}>
            <div className="row gap-2" style={{ marginBottom: 7 }}>
              <span className="sha">{index + 1}</span>
              <Icon name={item.icon} s={14} style={{ color: `var(--${item.tone})` }} />
              <b style={{ fontSize: "var(--t-13)" }}>{item.title}</b>
            </div>
            <p className="muted" style={{ fontSize: "var(--t-12)", lineHeight: 1.45, minHeight: 68, margin: 0 }}>
              {item.description}
            </p>
            <button
              className="btn btn-sm"
              style={{ marginTop: 10, width: "100%", justifyContent: "center" }}
              onClick={() => openNew(item.id)}
            >
              <Icon name="plus" s={10} /> Create
            </button>
          </div>
        ))}
      </div>

      <div className="h-section" style={{ marginBottom: 8 }}>
        <h2>My routines</h2>
        <span className="faint" style={{ fontSize: "var(--t-12)" }}>
          {routines.length} configured
        </span>
      </div>

      {(routinesQuery.isLoading || reposQuery.isLoading) && (
        <div className="card muted" style={{ padding: 18 }}>Loading routines…</div>
      )}
      {routinesQuery.isError && (
        <div className="card" style={{ padding: 18, color: "var(--danger)" }}>
          {routinesQuery.error?.detail || "Could not load routines"}
        </div>
      )}
      {!routinesQuery.isLoading && routines.length === 0 && (
        <div className="card" style={{ padding: 28, textAlign: "center" }}>
          <Icon name="jobs" s={26} style={{ color: "var(--fg-faint)", marginBottom: 8 }} />
          <div style={{ fontWeight: 600, marginBottom: 4 }}>No routines yet</div>
          <div className="muted" style={{ fontSize: "var(--t-13)", marginBottom: 12 }}>
            Start with a daily health check on a development branch, then chain review and promotion gates.
          </div>
          <button className="btn btn-primary" onClick={() => openNew("health_repair")}>
            <Icon name="plus" s={12} /> Create health routine
          </button>
        </div>
      )}
      <div className="col gap-2">
        {routines.map((routine) => (
          <RoutineCard
            key={routine.id}
            routine={routine}
            repo={repos.find((item) => item.id === routine.repo_id)}
            routines={routines}
            pending={pending}
            onEdit={(item) => {
              setEditing(item);
              setInitialKind(item.kind);
              setEditorOpen(true);
            }}
            onToggle={toggle}
            onDelete={remove}
            onMergeLock={changeMergeLock}
          />
        ))}
      </div>

      {definitionOnly && (
        <div className="card" style={{ padding: 14, marginTop: 16 }}>
          <div className="row gap-2" style={{ marginBottom: 5 }}>
            <Icon name="audit" s={14} />
            <b style={{ fontSize: "var(--t-13)" }}>Safe rollout boundary</b>
          </div>
          <span className="muted" style={{ fontSize: "var(--t-12)", lineHeight: 1.5 }}>
            This release stores and governs routine definitions but does not start a hidden scheduler.
            The next executor layer can reuse SelfRepair's existing job pipeline, review-pausing state,
            audit log, Git publisher, and this protected-branch merge guard.
          </span>
        </div>
      )}

      <RoutineEditor
        open={editorOpen}
        routine={editing}
        repos={repos}
        routines={routines}
        initialKind={initialKind}
        pending={createRoutine.isPending || patchRoutine.isPending}
        onClose={() => setEditorOpen(false)}
        onSave={save}
      />
    </div>
  );
}
