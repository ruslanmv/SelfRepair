import { Icon, Pill, Sparkline } from "../components/atoms.jsx";
import { useDashboard } from "../hooks/useDashboard.js";

// Decorative sparkline series generator (deterministic from a seed). These
// are purely visual flourishes on the KPI cards — the headline numbers
// beside them come from the real /v1/dashboard API, never from mock data.
const spark = (seed) => {
  const out = [];
  let v = 50 + (seed % 20);
  for (let i = 0; i < 24; i++) {
    v += Math.sin(seed + i * 0.7) * 8 + (i % 3 === 0 ? 6 : -3);
    v = Math.max(8, Math.min(96, v));
    out.push(v);
  }
  return out;
};

function percent(rate) {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return "—";
  return `${(Number(rate) * 100).toFixed(1)}%`;
}

function formatSeconds(s) {
  if (s === null || s === undefined) return "—";
  const sec = Math.round(Number(s));
  const m = Math.floor(sec / 60);
  const ss = sec % 60;
  if (m === 0) return `${ss}s`;
  return `${m}m ${ss}s`;
}

function money(v) {
  if (v === null || v === undefined) return "$0";
  return `$${Number(v).toFixed(2)}`;
}

function bandTone(band) {
  if (band === "90-100") return "ok";
  if (band === "70-89") return "info";
  if (band === "50-69") return "warn";
  return "danger";
}

export const Overview = ({ onNav, showHeroGradient = true }) => {
  const { data, isLoading, isError, error } = useDashboard();
  const kpis = data?.kpis || {};
  const fleet = data?.fleet_health || [];
  const cost = data?.repair_cost || {};
  const activity = data?.activity || [];
  const awaiting = data?.awaiting_approval || [];
  const totalFleet = fleet.reduce((a, b) => a + (b.count || 0), 0);

  const cards = [
    {
      label: "Repos under management",
      value: kpis.repos_total ?? "—",
      delta: "",
      series: spark(3),
      tone: "info",
    },
    {
      label: "Open findings",
      value: kpis.open_findings ?? "—",
      delta: "",
      series: spark(7),
      tone: "warn",
    },
    {
      label: "Auto-fix success rate",
      value: percent(kpis.auto_fix_success_rate),
      delta: `${kpis.sample_size ?? 0} sample`,
      series: spark(11),
      tone: "ok",
    },
    {
      label: "Mean time to repair",
      value: formatSeconds(kpis.mttr_seconds_avg),
      delta: "",
      series: spark(15),
      tone: "ok",
    },
  ];

  return (
    <div className="page-fade" style={{ padding: 20, position: "relative" }}>
      {showHeroGradient && (
        <div
          className="hero-bg"
          style={{
            position: "absolute",
            inset: "0 0 auto 0",
            height: 220,
            pointerEvents: "none",
            opacity: 0.55,
            zIndex: 0,
          }}
        />
      )}
      <div style={{ position: "relative", zIndex: 1 }}>
        <div
          className="row"
          style={{ justifyContent: "space-between", alignItems: "flex-end", marginBottom: 18 }}
        >
          <div>
            <div className="row gap-2" style={{ marginBottom: 6 }}>
              <span className="live">live · dashboard</span>
              {isError && (
                <span className="pill pill-danger" style={{ fontSize: 11 }}>
                  {error?.detail || "refresh failed"}
                </span>
              )}
            </div>
            <h1
              style={{
                margin: 0,
                fontSize: "var(--t-32)",
                letterSpacing: "-0.02em",
                fontWeight: 600,
              }}
            >
              Fleet overview
            </h1>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: "var(--t-14)" }}>
              {kpis.repos_total ?? 0} repos under management
            </p>
          </div>
          <div className="row gap-2">
            <button className="btn">
              <Icon name="retry" s={13} /> Refresh
            </button>
            <button className="btn btn-primary" onClick={() => onNav("repos")}>
              <Icon name="plus" s={13} /> Connect repo
            </button>
          </div>
        </div>

        {/* KPIs */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 12,
            marginBottom: 18,
          }}
        >
          {cards.map((kpi, i) => (
            <div key={i} className="card" style={{ padding: 14, position: "relative", overflow: "hidden" }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                <span
                  className="muted"
                  style={{
                    fontSize: "var(--t-12)",
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                  }}
                >
                  {kpi.label}
                </span>
              </div>
              <div className="row" style={{ alignItems: "flex-end", justifyContent: "space-between", gap: 10 }}>
                <div className="col" style={{ gap: 2 }}>
                  <span style={{ fontSize: "var(--t-32)", fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1 }}>
                    {isLoading ? "…" : kpi.value}
                  </span>
                  {kpi.delta && (
                    <span style={{ fontSize: "var(--t-12)", color: "var(--fg-muted)" }}>{kpi.delta}</span>
                  )}
                </div>
                <div
                  style={{
                    color:
                      kpi.tone === "ok" ? "var(--ok)" :
                      kpi.tone === "warn" ? "var(--warn)" :
                      "var(--cyan)",
                  }}
                >
                  <Sparkline data={kpi.series} w={96} h={32} fill />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Two-column block */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr",
            gap: 12,
            marginBottom: 18,
          }}
        >
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Fleet health distribution</h2>
              <span className="faint" style={{ fontSize: "var(--t-12)" }}>{totalFleet} repos</span>
            </div>
            <div className="col gap-3" style={{ marginTop: 12 }}>
              {fleet.map((b, i) => {
                const pct = totalFleet ? (b.count / totalFleet) * 100 : 0;
                const tone = bandTone(b.band);
                const color =
                  tone === "ok" ? "var(--ok)" :
                  tone === "info" ? "var(--info)" :
                  tone === "warn" ? "var(--warn)" : "var(--danger)";
                return (
                  <div key={i} className="row gap-3">
                    <span className="mono muted" style={{ width: 56, fontSize: "var(--t-12)" }}>{b.band}</span>
                    <div style={{ flex: 1, height: 14, background: "var(--bg-elev-2)", borderRadius: 4, overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: color, opacity: 0.85, borderRadius: 4 }} />
                    </div>
                    <span className="mono" style={{ width: 50, textAlign: "right", color }}>{b.count}</span>
                    <span className="faint mono" style={{ width: 40, textAlign: "right", fontSize: "var(--t-12)" }}>{pct.toFixed(0)}%</span>
                  </div>
                );
              })}
              {fleet.length === 0 && !isLoading && (
                <div className="muted">No repos in fleet yet.</div>
              )}
            </div>
            <div
              className="hairline-t"
              style={{
                marginTop: 14, paddingTop: 12, display: "flex",
                justifyContent: "flex-end", fontSize: "var(--t-12)",
              }}
            >
              <a className="muted" style={{ cursor: "pointer", color: "var(--cyan)" }} onClick={() => onNav("repos")}>
                View all repos →
              </a>
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Repair spend{cost.month_label ? ` · ${cost.month_label}` : ""}</h2>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 6 }}>
              <span style={{ fontSize: "var(--t-32)", fontWeight: 600, letterSpacing: "-0.02em" }}>
                {money(cost.spend_usd)}
              </span>
              <span className="muted">this month</span>
            </div>
            <div className="hairline-t" style={{ marginTop: 14, paddingTop: 12 }}>
              <div className="row" style={{ justifyContent: "space-between", fontSize: "var(--t-13)" }}>
                <span className="muted">Avg per repair</span>
                <span className="mono">{money(kpis.usd_per_repair_avg)}</span>
              </div>
              <div className="row" style={{ justifyContent: "space-between", fontSize: "var(--t-13)", marginTop: 4 }}>
                <span className="muted">Regression rate</span>
                <span className="mono">{percent(kpis.regression_rate)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom row: live activity + awaiting approval */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Live activity</h2>
              <span className="live" style={{ fontSize: 10 }}>streaming</span>
            </div>
            <div style={{ marginTop: 6 }}>
              {activity.length === 0 && (
                <div className="muted">No recent activity.</div>
              )}
              {activity.map((a, i) => {
                const color =
                  a.level === "error" ? "var(--danger)" :
                  a.level === "ok" ? "var(--ok)" :
                  a.level === "warn" ? "var(--warn)" : "var(--cyan)";
                return (
                  <div
                    key={a.event_id || i}
                    className="row gap-3"
                    style={{
                      padding: "8px 0",
                      borderBottom: i < activity.length - 1 ? "1px solid var(--hairline)" : "none",
                    }}
                  >
                    <span className="mono faint" style={{ fontSize: "var(--t-12)", width: 110 }} title={a.ts}>
                      {a.ts ? new Date(a.ts).toLocaleTimeString() : ""}
                    </span>
                    <span style={{ width: 6, height: 6, borderRadius: 999, background: color, marginRight: 2 }} />
                    <span style={{ flex: 1, fontSize: "var(--t-13)" }}>{a.message}</span>
                    <span className="mono muted" style={{ fontSize: "var(--t-12)" }}>{a.repo_full_name}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Needs my approval</h2>
              <span className="pill pill-warn">{awaiting.length}</span>
            </div>
            {awaiting.length === 0 && (
              <div className="muted">Nothing awaiting approval.</div>
            )}
            {awaiting.map((r) => (
              <div
                key={r.repair_id}
                className="row gap-3"
                style={{ padding: "10px 0", borderBottom: "1px solid var(--hairline)", cursor: "pointer" }}
                onClick={() => onNav("repair", r.repair_id)}
              >
                <Pill tone="warn" dot>Awaiting</Pill>
                <div className="col grow" style={{ minWidth: 0 }}>
                  <span className="truncate" style={{ fontSize: "var(--t-13)" }}>
                    {r.fixer_id}
                  </span>
                  <span className="faint truncate" style={{ fontSize: "var(--t-12)" }}>
                    {r.repo?.full_name || r.repair_id?.slice(0, 8)} · {r.finding?.kind}
                  </span>
                </div>
                <span className="sha">{money(r.cost_usd)}</span>
                <Icon name="caret" s={14} style={{ color: "var(--fg-faint)" }} />
              </div>
            ))}
            <div style={{ paddingTop: 10, fontSize: "var(--t-13)" }}>
              <a className="muted" style={{ cursor: "pointer", color: "var(--cyan)" }} onClick={() => onNav("repairs")}>
                View all repairs →
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
