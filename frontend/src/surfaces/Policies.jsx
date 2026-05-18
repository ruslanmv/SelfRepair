import { Pill } from "../components/atoms.jsx";
import { usePolicies, usePolicyDecisions } from "../hooks/usePolicies.js";

function outcomeTone(outcome) {
  if (outcome === "allow") return "ok";
  if (outcome === "deny") return "danger";
  return "info";
}

export function Policies() {
  const versions = usePolicies();
  const decisions = usePolicyDecisions({ limit: 50 });
  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
        Policies
      </h1>
      <p
        className="muted"
        style={{ margin: "2px 0 18px", fontSize: "var(--t-13)" }}
      >
        OPA bundle versions and recent policy decisions across the fleet.
      </p>

      <h2 style={{ fontSize: 16, margin: "6px 0 8px" }}>Bundle versions</h2>
      <div
        className="card"
        style={{ padding: 0, overflow: "hidden", marginBottom: 24 }}
      >
        {versions.isLoading && (
          <div className="muted" style={{ padding: 16 }}>
            Loading…
          </div>
        )}
        {versions.isError && (
          <div
            className="muted"
            style={{ padding: 16, color: "var(--danger)" }}
          >
            {versions.error?.detail || "Could not load policies"}
          </div>
        )}
        {versions.data?.items?.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No policy bundles uploaded yet.
          </div>
        )}
        {versions.data?.items?.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>Version</th>
                <th>SHA</th>
                <th>Description</th>
                <th style={{ width: 180 }}>Created</th>
                <th style={{ width: 180 }}>Deployed</th>
              </tr>
            </thead>
            <tbody>
              {versions.data.items.map((v) => (
                <tr key={v.id}>
                  <td className="mono">{v.version}</td>
                  <td className="mono muted">{v.bundle_sha?.slice(0, 12)}</td>
                  <td>{v.description}</td>
                  <td className="muted">{v.created_at}</td>
                  <td className="muted">{v.deployed_at || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2 style={{ fontSize: 16, margin: "6px 0 8px" }}>Recent decisions</h2>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {decisions.isLoading && (
          <div className="muted" style={{ padding: 16 }}>
            Loading…
          </div>
        )}
        {decisions.data?.items?.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No decisions recorded yet.
          </div>
        )}
        {decisions.data?.items?.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>Repair</th>
                <th>Rule</th>
                <th style={{ width: 110 }}>Outcome</th>
                <th style={{ width: 130 }}>Approval</th>
                <th style={{ width: 200 }}>Decided</th>
              </tr>
            </thead>
            <tbody>
              {decisions.data.items.map((d) => (
                <tr key={d.id}>
                  <td className="mono">{d.repair_id?.slice(0, 8)}</td>
                  <td className="mono muted">{d.rule_id}</td>
                  <td>
                    <Pill tone={outcomeTone(d.outcome)}>{d.outcome}</Pill>
                  </td>
                  <td className="muted">
                    {d.requires_approval ? "required" : "not required"}
                  </td>
                  <td className="muted">{d.decided_at || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
