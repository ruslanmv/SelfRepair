import { Pill, StateBadge } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const Jobs = ({ onNav }) => (
  <div className="page-fade" style={{ padding: "16px 20px" }}>
    <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>Jobs</h1>
        <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
          <span className="live" style={{ fontSize: 11 }}>2 running</span> · 1 queued · 1.4k completed today
        </p>
      </div>
    </div>
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
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
            <th style={{ width: 80 }}>Events</th>
          </tr>
        </thead>
        <tbody>
          {D.jobs.map((j) => (
            <tr key={j.id} onClick={() => onNav("job", j.id)} className={j.id === "J-77821" ? "is-selected" : ""}>
              <td className="mono">{j.id}</td>
              <td className="muted">{j.repo}</td>
              <td className="mono muted" style={{ fontSize: "var(--t-12)" }}>{j.trigger}</td>
              <td><StateBadge state={j.state} /></td>
              <td><Pill>{j.stage}</Pill></td>
              <td className="muted" style={{ fontSize: "var(--t-12)" }}>{j.started}</td>
              <td className="mono">{j.duration}</td>
              <td className="mono muted">{j.events}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);
