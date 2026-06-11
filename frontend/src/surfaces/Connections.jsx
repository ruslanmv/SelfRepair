import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Pill } from "../components/atoms.jsx";
import {
  listConnections,
  saveConnection,
  testConnection,
} from "../api/connections.js";

function statusTone(status) {
  if (status === "ok") return "ok";
  if (status === "error") return "danger";
  return "info";
}

const inputStyle = {
  width: "100%",
  padding: "9px 10px",
  border: "1px solid var(--border, #2a2f3a)",
  borderRadius: 6,
  background: "var(--bg-elev, #11141a)",
  color: "var(--fg, #e6e8ee)",
  fontSize: 14,
  outline: "none",
};

function ConnectionCard({ conn, onSaved }) {
  const qc = useQueryClient();
  const [baseUrl, setBaseUrl] = React.useState(conn.base_url || "");
  const [apiKey, setApiKey] = React.useState("");

  const save = useMutation({
    mutationFn: () =>
      saveConnection(conn.provider, {
        base_url: baseUrl,
        ...(apiKey ? { api_key: apiKey } : {}),
      }),
    onSuccess: () => {
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["connections"] });
      onSaved?.();
    },
  });

  const test = useMutation({
    mutationFn: () => testConnection(conn.provider),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  });

  const busy = save.isPending || test.isPending;

  return (
    <div className="card" style={{ padding: 16, marginBottom: 16 }}>
      <div className="row" style={{ alignItems: "center", gap: 10, marginBottom: 4 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>{conn.label}</h3>
        <span className="mono muted" style={{ fontSize: 11 }}>{conn.provider}</span>
        <div style={{ flex: 1 }} />
        <Pill tone={statusTone(conn.status)} dot>
          {conn.status}
        </Pill>
      </div>
      {conn.detail && (
        <p className="muted" style={{ margin: "0 0 12px", fontSize: 12 }}>
          {conn.detail}
        </p>
      )}

      <label style={{ display: "block", fontSize: 12, margin: "8px 0 6px" }}>
        Base URL
      </label>
      <input
        type="text"
        value={baseUrl}
        placeholder={conn.default_url}
        onChange={(e) => setBaseUrl(e.target.value)}
        style={inputStyle}
      />

      <label style={{ display: "block", fontSize: 12, margin: "12px 0 6px" }}>
        API key{" "}
        {conn.has_secret && (
          <span className="muted mono" style={{ fontSize: 11 }}>
            (saved: {conn.masked_secret})
          </span>
        )}
      </label>
      <input
        type="password"
        value={apiKey}
        autoComplete="off"
        placeholder={conn.has_secret ? "Leave blank to keep current key" : "Enter API key"}
        onChange={(e) => setApiKey(e.target.value)}
        style={inputStyle}
      />

      <div className="row" style={{ gap: 8, marginTop: 14 }}>
        <button
          className="btn btn-primary"
          onClick={() => save.mutate()}
          disabled={busy}
        >
          {save.isPending ? "Saving…" : "Save & Test"}
        </button>
        <button
          className="btn"
          onClick={() => test.mutate()}
          disabled={busy}
        >
          {test.isPending ? "Testing…" : "Test"}
        </button>
        {conn.last_checked_at && (
          <span className="muted" style={{ fontSize: 11, alignSelf: "center" }}>
            Last checked {new Date(conn.last_checked_at).toLocaleString()}
          </span>
        )}
      </div>
      {(save.isError || test.isError) && (
        <p style={{ marginTop: 10, fontSize: 12, color: "var(--danger, #f06d75)" }}>
          {String(
            (save.error || test.error)?.detail ||
              (save.error || test.error)?.message ||
              "Request failed.",
          )}
        </p>
      )}
    </div>
  );
}

export function Connections() {
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: () => listConnections(),
  });

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
        Connections
      </h1>
      <p className="muted" style={{ margin: "2px 0 18px", fontSize: "var(--t-13)" }}>
        Wire SelfRepair to OllaBridge, GitPilot and MatrixLab. Secrets are
        encrypted at rest and never displayed.
      </p>

      {connections.isLoading && <div className="muted">Loading…</div>}
      {connections.isError && (
        <div className="muted" style={{ color: "var(--danger, #f06d75)" }}>
          Could not load connections.
        </div>
      )}
      {connections.data?.map((conn) => (
        <ConnectionCard key={conn.provider} conn={conn} />
      ))}
    </div>
  );
}
