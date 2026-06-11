import React from "react";

import {
  ErrorState,
  LoadingState,
} from "../../components/StateScreens.jsx";
import { useAdminStats } from "../../hooks/useAdmin.js";

function StatCard({ label, value }) {
  return (
    <div className="card" style={{ padding: 16, minWidth: 0 }}>
      <div
        className="faint"
        style={{
          fontSize: 11,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{value}</div>
    </div>
  );
}

function BackendPill({ label, value }) {
  // value: string (db dialect) or boolean (redis/email configured).
  let tone = "neutral";
  let text = String(value);
  if (typeof value === "boolean") {
    tone = value ? "ok" : "danger";
    text = value ? "Configured" : "Not configured";
  } else {
    tone = "info";
  }
  return (
    <div
      className="card"
      style={{
        padding: "12px 14px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 10,
      }}
    >
      <span style={{ fontWeight: 600 }}>{label}</span>
      <span className={`pill pill-${tone}`}>
        <span className="pill-dot" />
        {text}
      </span>
    </div>
  );
}

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

export function AdminSystem() {
  const stats = useAdminStats();

  if (stats.isLoading && !stats.data) {
    return <LoadingState label="Loading system status…" />;
  }
  if (stats.isError) {
    return (
      <ErrorState
        title="Could not load system status"
        message={stats.error?.detail || "Please retry."}
        onRetry={() => stats.refetch()}
      />
    );
  }

  const d = stats.data || {};
  const u = d.users || {};
  const b = d.backends || {};
  const signups = d.recent_signups || [];

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
          System
        </h1>
        <p
          className="muted"
          style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
        >
          Live counts and backend status for the SelfRepair control plane.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <StatCard label="Users" value={u.total ?? 0} />
        <StatCard label="Verified" value={u.verified ?? 0} />
        <StatCard label="Active" value={u.active ?? 0} />
        <StatCard label="Admins" value={u.admins ?? 0} />
        <StatCard label="Messages" value={d.messages ?? 0} />
        <StatCard label="Jobs" value={d.jobs ?? 0} />
        <StatCard label="Unread notifs" value={d.notifications_unread ?? 0} />
      </div>

      <h2
        style={{ margin: "0 0 10px", fontSize: "var(--t-16)", fontWeight: 600 }}
      >
        Backends
      </h2>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <BackendPill label="Database" value={b.db ?? "unknown"} />
        <BackendPill label="Redis" value={Boolean(b.redis)} />
        <BackendPill label="Email" value={Boolean(b.email)} />
      </div>

      <h2
        style={{ margin: "0 0 10px", fontSize: "var(--t-16)", fontWeight: 600 }}
      >
        Recent signups
      </h2>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {signups.length === 0 ? (
          <div className="muted" style={{ padding: 16 }}>
            No signups yet.
          </div>
        ) : (
          <div className="scroll-x-mobile" style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Email</th>
                  <th style={{ width: 160 }}>Username</th>
                  <th style={{ width: 200 }}>Created</th>
                </tr>
              </thead>
              <tbody>
                {signups.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 600 }}>{s.email}</td>
                    <td className="mono muted">@{s.username}</td>
                    <td className="muted">{fmtDate(s.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
