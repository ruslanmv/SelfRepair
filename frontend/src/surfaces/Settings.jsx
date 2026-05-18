import React from "react";

import { Pill } from "../components/atoms.jsx";
import {
  useConnectIntegration,
  useDisconnectIntegration,
  useIntegrations,
} from "../hooks/useIntegrations.js";
import { useSession } from "../hooks/useSession.js";

function statusTone(status) {
  if (status === "active") return "ok";
  if (status === "revoked") return "muted";
  if (status === "error") return "danger";
  return "info";
}

export function Settings() {
  const me = useSession();
  const integrations = useIntegrations();
  const connect = useConnectIntegration();
  const disconnect = useDisconnectIntegration();

  const [provider, setProvider] = React.useState("github");
  const [displayName, setDisplayName] = React.useState("");
  const [credentialRef, setCredentialRef] = React.useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!displayName || !credentialRef) return;
    try {
      await connect.mutateAsync({
        provider,
        body: { display_name: displayName, credential_ref: credentialRef },
      });
      setDisplayName("");
      setCredentialRef("");
    } catch {
      /* surfaced via connect.error */
    }
  };

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
        Settings
      </h1>
      <p
        className="muted"
        style={{ margin: "2px 0 18px", fontSize: "var(--t-13)" }}
      >
        Workspace, integrations, and account.
      </p>

      <h2 style={{ fontSize: 16, margin: "6px 0 8px" }}>Account</h2>
      <div className="card" style={{ padding: 16, marginBottom: 24 }}>
        {me.data ? (
          <div className="row" style={{ gap: 24 }}>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>Email</div>
              <div className="mono">{me.data.user.email}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>Role</div>
              <div>{me.data.user.role}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>Org</div>
              <div>{me.data.org.name}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>Plan</div>
              <div>{me.data.org.plan}</div>
            </div>
          </div>
        ) : (
          <div className="muted">
            Not signed in. The dev org pin is used until you authenticate.
          </div>
        )}
      </div>

      <h2 style={{ fontSize: 16, margin: "6px 0 8px" }}>Integrations</h2>
      <div
        className="card"
        style={{ padding: 0, overflow: "hidden", marginBottom: 16 }}
      >
        {integrations.isLoading && (
          <div className="muted" style={{ padding: 16 }}>
            Loading…
          </div>
        )}
        {integrations.data?.items?.length === 0 && (
          <div className="muted" style={{ padding: 16 }}>
            No integrations connected.
          </div>
        )}
        {integrations.data?.items?.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 110 }}>Provider</th>
                <th>Name</th>
                <th>Account</th>
                <th style={{ width: 110 }}>Status</th>
                <th style={{ width: 90 }}></th>
              </tr>
            </thead>
            <tbody>
              {integrations.data.items.map((i) => (
                <tr key={i.id}>
                  <td className="mono">{i.provider}</td>
                  <td>{i.display_name}</td>
                  <td className="muted">{i.account || "—"}</td>
                  <td>
                    <Pill tone={statusTone(i.status)}>{i.status}</Pill>
                  </td>
                  <td>
                    {i.deleted_at ? null : (
                      <button
                        className="btn"
                        onClick={() => disconnect.mutate(i.id)}
                        disabled={disconnect.isPending}
                      >
                        Disconnect
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form onSubmit={submit} className="card" style={{ padding: 16 }}>
        <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>
          Connect a new integration
        </h3>
        <p
          className="muted"
          style={{ margin: "0 0 12px", fontSize: 12 }}
        >
          The credential reference is a pointer to your secret manager (env
          name, KMS ARN, Vault path) — the actual token is never sent to
          the API.
        </p>
        <div className="row" style={{ gap: 8, alignItems: "flex-end" }}>
          <div>
            <div
              className="muted"
              style={{ fontSize: 12, marginBottom: 4 }}
            >
              Provider
            </div>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              style={{ padding: "6px 8px" }}
            >
              <option value="github">github</option>
              <option value="gitlab">gitlab</option>
              <option value="huggingface">huggingface</option>
              <option value="bitbucket">bitbucket</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <div
              className="muted"
              style={{ fontSize: 12, marginBottom: 4 }}
            >
              Display name
            </div>
            <input
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              style={{ width: "100%", padding: "6px 8px" }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <div
              className="muted"
              style={{ fontSize: 12, marginBottom: 4 }}
            >
              Credential ref
            </div>
            <input
              required
              value={credentialRef}
              onChange={(e) => setCredentialRef(e.target.value)}
              placeholder="env:GITHUB_PAT"
              style={{ width: "100%", padding: "6px 8px" }}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={connect.isPending}
          >
            {connect.isPending ? "Connecting…" : "Connect"}
          </button>
        </div>
        {connect.isError && (
          <div
            style={{
              marginTop: 10,
              fontSize: 13,
              color: "var(--danger)",
            }}
          >
            {connect.error?.detail || "Could not connect integration"}
          </div>
        )}
      </form>
    </div>
  );
}
