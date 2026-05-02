import { Icon, Pill, StateBadge } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const Repairs = ({ onNav }) => (
  <div className="page-fade" style={{ padding: "16px 20px" }}>
    <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>Repairs</h1>
        <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
          Pull requests opened by SelfRepair · 3 awaiting your approval
        </p>
      </div>
    </div>
    <div className="row gap-2" style={{ marginBottom: 10 }}>
      <span className="chip is-active">all · 23</span>
      <span className="chip">awaiting approval · 3</span>
      <span className="chip">in sandbox · 1</span>
      <span className="chip">merged · 14</span>
      <span className="chip">blocked · 1</span>
    </div>
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="tbl">
        <thead>
          <tr>
            <th>Repair</th>
            <th style={{ width: 200 }}>Repo</th>
            <th style={{ width: 160 }}>State</th>
            <th style={{ width: 100 }}>Diff</th>
            <th style={{ width: 100 }}>Cost</th>
            <th style={{ width: 100 }}>Signed</th>
            <th style={{ width: 90 }}>Opened</th>
          </tr>
        </thead>
        <tbody>
          {D.repairs.map((r) => (
            <tr key={r.id} className={r.id === "PR-2210" ? "is-selected" : ""} onClick={() => onNav("repair", r.id)}>
              <td>
                <div className="row gap-2">
                  <Icon name="repairs" s={13} style={{ color: "var(--fg-muted)" }} />
                  <div className="col">
                    <span style={{ fontSize: "var(--t-13)" }}>{r.title}</span>
                    <span className="faint mono" style={{ fontSize: "var(--t-12)" }}>{r.id} · {r.policy}</span>
                  </div>
                </div>
              </td>
              <td className="muted">{r.repo}</td>
              <td><StateBadge state={r.state} /></td>
              <td>
                <span className="mono">
                  <span style={{ color: "var(--ok)" }}>+{r.lines.added}</span>{" "}
                  <span style={{ color: "var(--danger)" }}>−{r.lines.removed}</span>
                </span>
              </td>
              <td className="mono muted">${r.cost.toFixed(3)}</td>
              <td>{r.signed ? <Pill tone="ok">✓ Sigstore</Pill> : <Pill>—</Pill>}</td>
              <td className="muted" style={{ fontSize: "var(--t-12)" }}>{r.opened}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);
