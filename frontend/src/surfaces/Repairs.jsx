import React from "react";

import { Icon, Pill, StateBadge } from "../components/atoms.jsx";
import { useRepairs } from "../hooks/useRepairs.js";

const STATE_FILTERS = [
  { id: undefined, label: "all" },
  { id: "published", label: "awaiting approval" },
  { id: "applied", label: "in sandbox" },
  { id: "merged", label: "merged" },
  { id: "failed", label: "failed" },
];

export const Repairs = ({ onNav }) => {
  const [stateFilter, setStateFilter] = React.useState(undefined);
  const params = { state: stateFilter, limit: 100 };
  const { data, isLoading, isError, error } = useRepairs(params);
  const items = data?.items || [];

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", marginBottom: 12 }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
            Repairs
          </h1>
          <p
            className="muted"
            style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
          >
            Pull requests opened by SelfRepair
          </p>
        </div>
      </div>
      <div className="row gap-2" style={{ marginBottom: 10, flexWrap: "wrap" }}>
        {STATE_FILTERS.map((f) => (
          <span
            key={f.label}
            className={`chip ${stateFilter === f.id ? "is-active" : ""}`}
            onClick={() => setStateFilter(f.id)}
          >
            {f.label}
          </span>
        ))}
      </div>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {isLoading && (
          <div className="muted" style={{ padding: 16 }}>Loading…</div>
        )}
        {isError && (
          <div
            className="muted"
            style={{ padding: 16, color: "var(--danger)" }}
          >
            {error?.detail || "Could not load repairs"}
          </div>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No repairs match these filters.
          </div>
        )}
        {items.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>Repair</th>
                <th style={{ width: 220 }}>Repo</th>
                <th style={{ width: 160 }}>State</th>
                <th style={{ width: 100 }}>Mode</th>
                <th style={{ width: 100 }}>Cost</th>
                <th style={{ width: 100 }}>Signed</th>
                <th style={{ width: 200 }}>Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => onNav("repair", r.id)}
                >
                  <td>
                    <div className="row gap-2">
                      <Icon
                        name="repairs"
                        s={13}
                        style={{ color: "var(--fg-muted)" }}
                      />
                      <div className="col">
                        <span style={{ fontSize: "var(--t-13)" }}>
                          {r.fixer_id}
                        </span>
                        <span
                          className="faint mono"
                          style={{ fontSize: "var(--t-12)" }}
                        >
                          {r.id?.slice(0, 8)} · {r.finding?.kind || r.finding_id?.slice(0, 8)}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="muted">{r.repo?.full_name || r.job?.id?.slice(0, 8)}</td>
                  <td><StateBadge state={r.state} /></td>
                  <td className="mono muted">{r.mode}</td>
                  <td className="mono muted">${(r.cost_usd || 0).toFixed(3)}</td>
                  <td>
                    {r.signed_commit_sha ? (
                      <Pill tone="ok">Sigstore</Pill>
                    ) : (
                      <Pill>—</Pill>
                    )}
                  </td>
                  <td
                    className="muted"
                    style={{ fontSize: "var(--t-12)" }}
                    title={r.created_at}
                  >
                    {r.created_at
                      ? new Date(r.created_at).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
