import { Icon, Pill, SeverityDot, StateBadge } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const Findings = () => (
  <div className="page-fade" style={{ padding: "16px 20px" }}>
    <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>Findings</h1>
        <p className="muted" style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}>
          Fleet-wide, grouped by fingerprint · 342 open · 1,118 closed (30d)
        </p>
      </div>
      <div className="row gap-2">
        <button className="btn">Bulk suppress…</button>
        <button className="btn btn-primary">Open triage queue</button>
      </div>
    </div>
    <div className="row gap-2" style={{ marginBottom: 10 }}>
      <span className="chip is-active">all</span>
      <span className="chip">critical · 12</span>
      <span className="chip">high · 38</span>
      <span className="chip">medium · 142</span>
      <span className="chip">low · 150</span>
      <span className="grow" />
      <span className="chip">+ Group by</span>
    </div>
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 32 }}><input type="checkbox" /></th>
            <th style={{ width: 28 }}>Sev</th>
            <th>Fingerprint · kind</th>
            <th style={{ width: 220 }}>Repo</th>
            <th style={{ width: 80 }}>Count</th>
            <th style={{ width: 110 }}>First seen</th>
            <th style={{ width: 140 }}>Suggested</th>
            <th style={{ width: 130 }}>State</th>
            <th style={{ width: 100 }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {D.findings.map((f) => (
            <tr key={f.fp}>
              <td><input type="checkbox" /></td>
              <td><SeverityDot level={f.severity} /></td>
              <td>
                <div className="col">
                  <span className="mono" style={{ fontSize: "var(--t-13)" }}>{f.kind}</span>
                  <span className="faint mono" style={{ fontSize: "var(--t-12)" }}>{f.fp} · {f.path}</span>
                </div>
              </td>
              <td className="muted">{f.repo}</td>
              <td className="mono">×{f.count}</td>
              <td className="muted" style={{ fontSize: "var(--t-12)" }}>{f.firstSeen}</td>
              <td><Pill tone={f.suggested.startsWith("auto") ? "ok" : f.suggested === "llm-assist" ? "info" : "neutral"}>{f.suggested}</Pill></td>
              <td><StateBadge state={f.state} /></td>
              <td><button className="btn btn-sm"><Icon name="caret" s={11} /> Triage</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);
