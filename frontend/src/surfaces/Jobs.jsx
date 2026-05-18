import { Pill, StateBadge } from "../components/atoms.jsx";
import { useJobs } from "../hooks/useJobs.js";

function formatDuration(startedAt, finishedAt) {
  if (!startedAt) return "—";
  const start = new Date(startedAt);
  const end = finishedAt ? new Date(finishedAt) : new Date();
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  const h = Math.floor(m / 60);
  return h
    ? `${String(h).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatStarted(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // Compact relative-ish formatting; full time is on hover.
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const Jobs = ({ onNav }) => {
  const { data, isLoading, isError, error } = useJobs({ limit: 100 });
  const items = data?.items || [];
  const running = items.filter((j) => [
    "queued", "cloning", "analyzing", "scanning", "planning",
    "repairing", "validating", "publishing",
  ].includes(j.state));
  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>Jobs</h1>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
            <span className="live" style={{ fontSize: 11 }}>{running.length} running</span> · {data?.count || 0} loaded
          </p>
        </div>
      </div>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {isLoading && (
          <div className="muted" style={{ padding: 16 }}>Loading…</div>
        )}
        {isError && (
          <div className="muted" style={{ padding: 16, color: "var(--danger)" }}>
            {error?.detail || "Could not load jobs"}
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>No jobs yet.</div>
        )}
        {items.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>Job</th>
                <th>Repo</th>
                <th style={{ width: 130 }}>Trigger</th>
                <th style={{ width: 130 }}>State</th>
                <th style={{ width: 100 }}>Stage</th>
                <th style={{ width: 110 }}>Started</th>
                <th style={{ width: 100 }}>Duration</th>
                <th style={{ width: 100 }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {items.map((j) => (
                <tr key={j.id} onClick={() => onNav("job", j.id)}>
                  <td className="mono">{j.id?.slice(0, 8)}</td>
                  <td className="muted">{j.repo?.full_name || j.repo_id}</td>
                  <td className="mono muted" style={{ fontSize: "var(--t-12)" }}>{j.trigger}</td>
                  <td><StateBadge state={j.state} /></td>
                  <td><Pill>{j.state}</Pill></td>
                  <td className="muted" style={{ fontSize: "var(--t-12)" }} title={j.started_at}>
                    {formatStarted(j.started_at)}
                  </td>
                  <td className="mono">{formatDuration(j.started_at, j.finished_at)}</td>
                  <td className="mono muted">{j.error_kind || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
