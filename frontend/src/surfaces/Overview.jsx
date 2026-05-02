import { HealthBar, Icon, Pill, Sparkline } from "../components/atoms.jsx";
import { SR_DATA as D } from "../data/mock.js";

export const Overview = ({ onNav, showHeroGradient = true }) => {
  const k = D.dashboard.kpis;
  const totalFleet = D.dashboard.fleetHealth.reduce((a, b) => a + b.count, 0);

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
              <span className="live">live · 2 jobs running</span>
              <span className="faint" style={{ fontSize: "var(--t-12)" }}>
                · last sync 14s ago
              </span>
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
              1,284 repos under management · 4 platforms · 38 active policies
            </p>
          </div>
          <div className="row gap-2">
            <button className="btn">
              <Icon name="retry" s={13} /> Refresh
            </button>
            <button className="btn btn-primary">
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
          {k.map((kpi, i) => (
            <div
              key={i}
              className="card"
              style={{ padding: 14, position: "relative", overflow: "hidden" }}
            >
              <div
                className="row"
                style={{ justifyContent: "space-between", marginBottom: 6 }}
              >
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
              <div
                className="row"
                style={{ alignItems: "flex-end", justifyContent: "space-between", gap: 10 }}
              >
                <div className="col" style={{ gap: 2 }}>
                  <span
                    style={{
                      fontSize: "var(--t-32)",
                      fontWeight: 600,
                      letterSpacing: "-0.02em",
                      lineHeight: 1,
                    }}
                  >
                    {kpi.value}
                  </span>
                  <span
                    style={{
                      fontSize: "var(--t-12)",
                      color:
                        kpi.tone === "ok"
                          ? "var(--ok)"
                          : kpi.tone === "warn"
                            ? "var(--warn)"
                            : "var(--fg-muted)",
                    }}
                  >
                    {kpi.delta}
                  </span>
                </div>
                <div
                  style={{
                    color:
                      kpi.tone === "ok"
                        ? "var(--ok)"
                        : kpi.tone === "warn"
                          ? "var(--warn)"
                          : "var(--cyan)",
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
              <span className="faint" style={{ fontSize: "var(--t-12)" }}>
                {totalFleet} repos
              </span>
            </div>
            <div className="col gap-3" style={{ marginTop: 12 }}>
              {D.dashboard.fleetHealth.map((b, i) => {
                const pct = (b.count / totalFleet) * 100;
                const color =
                  b.tone === "ok"
                    ? "var(--ok)"
                    : b.tone === "warn"
                      ? "var(--warn)"
                      : b.tone === "danger"
                        ? "var(--danger)"
                        : "var(--info)";
                return (
                  <div key={i} className="row gap-3">
                    <span
                      className="mono muted"
                      style={{ width: 56, fontSize: "var(--t-12)" }}
                    >
                      {b.band}
                    </span>
                    <div
                      style={{
                        flex: 1,
                        height: 14,
                        background: "var(--bg-elev-2)",
                        borderRadius: 4,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${pct}%`,
                          height: "100%",
                          background: color,
                          opacity: 0.85,
                          borderRadius: 4,
                        }}
                      />
                    </div>
                    <span
                      className="mono"
                      style={{ width: 50, textAlign: "right", color }}
                    >
                      {b.count}
                    </span>
                    <span
                      className="faint mono"
                      style={{ width: 40, textAlign: "right", fontSize: "var(--t-12)" }}
                    >
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                );
              })}
            </div>
            <div
              className="hairline-t"
              style={{
                marginTop: 14,
                paddingTop: 12,
                display: "flex",
                justifyContent: "space-between",
                fontSize: "var(--t-12)",
              }}
            >
              <span className="muted">
                Median health{" "}
                <span className="mono" style={{ color: "var(--fg)" }}>
                  78
                </span>
              </span>
              <span className="muted">
                7d change <span style={{ color: "var(--ok)" }}>+3.2</span>
              </span>
              <a
                className="muted"
                style={{ cursor: "pointer", color: "var(--cyan)" }}
                onClick={() => onNav("repos")}
              >
                View all repos →
              </a>
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Repair spend · {D.dashboard.repairCost.monthLabel}</h2>
            </div>
            <div
              style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 6 }}
            >
              <span
                style={{
                  fontSize: "var(--t-32)",
                  fontWeight: 600,
                  letterSpacing: "-0.02em",
                }}
              >
                {D.dashboard.repairCost.spend}
              </span>
              <span className="muted">of {D.dashboard.repairCost.budget}</span>
            </div>
            <div
              style={{
                height: 8,
                background: "var(--bg-elev-2)",
                borderRadius: 4,
                overflow: "hidden",
                marginTop: 12,
              }}
            >
              <div
                style={{
                  width: "24%",
                  height: "100%",
                  background: "var(--grad-brand)",
                }}
              />
            </div>
            <div
              className="row"
              style={{ justifyContent: "space-between", marginTop: 8, fontSize: "var(--t-12)" }}
            >
              <span className="muted">24% used · 6 days in</span>
              <span className="muted">on track</span>
            </div>
            <div className="hairline-t" style={{ marginTop: 14, paddingTop: 12 }}>
              <div
                className="row"
                style={{
                  justifyContent: "space-between",
                  fontSize: "var(--t-13)",
                  marginBottom: 6,
                }}
              >
                <span className="muted">By policy</span>
                <span className="muted">tokens</span>
              </div>
              {[
                { l: "auto-fix:* (templates)", v: 184204, c: "var(--ok)" },
                { l: "llm-assist:repair", v: 92448, c: "var(--info)" },
                { l: "policy-evaluate", v: 41092, c: "var(--violet)" },
              ].map((r, i) => (
                <div
                  key={i}
                  className="row gap-3"
                  style={{ padding: "5px 0", fontSize: "var(--t-13)" }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: r.c,
                    }}
                  />
                  <span style={{ flex: 1 }}>{r.l}</span>
                  <span className="mono muted">{r.v.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom row: live activity + escalations */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Live activity</h2>
              <span className="live" style={{ fontSize: 10 }}>
                streaming
              </span>
            </div>
            <div style={{ marginTop: 6 }}>
              {D.dashboard.activity.map((a, i) => {
                const color =
                  a.tone === "ok"
                    ? "var(--ok)"
                    : a.tone === "danger"
                      ? "var(--danger)"
                      : a.tone === "info"
                        ? "var(--cyan)"
                        : "var(--fg-faint)";
                return (
                  <div
                    key={i}
                    className="row gap-3"
                    style={{
                      padding: "8px 0",
                      borderBottom:
                        i < D.dashboard.activity.length - 1
                          ? "1px solid var(--hairline)"
                          : "none",
                    }}
                  >
                    <span
                      className="mono faint"
                      style={{ fontSize: "var(--t-12)", width: 70 }}
                    >
                      {a.t}
                    </span>
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: 999,
                        background: color,
                        marginRight: 2,
                      }}
                    />
                    <span style={{ flex: 1, fontSize: "var(--t-13)" }}>{a.text}</span>
                    <span className="mono muted" style={{ fontSize: "var(--t-12)" }}>
                      {a.repo}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div className="h-section">
              <h2>Needs my approval</h2>
              <span className="pill pill-warn">3</span>
            </div>
            {D.repairs
              .filter((r) => r.state === "awaiting-approval")
              .map((r, i) => (
                <div
                  key={i}
                  className="row gap-3"
                  style={{
                    padding: "10px 0",
                    borderBottom: "1px solid var(--hairline)",
                    cursor: "pointer",
                  }}
                  onClick={() => onNav("repair", r.id)}
                >
                  <Pill tone="warn" dot>
                    Awaiting
                  </Pill>
                  <div className="col grow" style={{ minWidth: 0 }}>
                    <span className="truncate" style={{ fontSize: "var(--t-13)" }}>
                      {r.title}
                    </span>
                    <span
                      className="faint truncate"
                      style={{ fontSize: "var(--t-12)" }}
                    >
                      {r.repo} · {r.id} · opened {r.opened}
                    </span>
                  </div>
                  <span className="sha">
                    +{r.lines.added}/−{r.lines.removed}
                  </span>
                  <Icon
                    name="caret"
                    s={14}
                    style={{ color: "var(--fg-faint)" }}
                  />
                </div>
              ))}
            <div style={{ paddingTop: 10, fontSize: "var(--t-13)" }}>
              <a
                className="muted"
                style={{ cursor: "pointer", color: "var(--cyan)" }}
                onClick={() => onNav("repairs")}
              >
                View all repairs →
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
