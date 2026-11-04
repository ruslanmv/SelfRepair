import React from "react";
import { useQuery } from "@tanstack/react-query";

import { Pill } from "../components/atoms.jsx";
import { listConnections } from "../api/connections.js";
import { ConnectorHub } from "../features/ConnectorHub.jsx";
import {
  useConnectIntegration,
  useDisconnectIntegration,
  useIntegrations,
} from "../hooks/useIntegrations.js";
import { useSession } from "../hooks/useSession.js";

const SERVICE_PROVIDERS = new Set(["ollabridge", "gitpilot", "matrixlab"]);
const SCM_PROVIDERS = ["github", "gitlab", "huggingface", "bitbucket"];

function statusTone(status) {
  if (status === "active") return "ok";
  if (status === "error") return "danger";
  return "neutral";
}

function SourceControlIntegrations({ items }) {
  const connect = useConnectIntegration();
  const disconnect = useDisconnectIntegration();
  const [provider, setProvider] = React.useState("github");
  const [displayName, setDisplayName] = React.useState("");
  const [credentialRef, setCredentialRef] = React.useState("");

  async function submit(event) {
    event.preventDefault();
    if (!displayName.trim() || !credentialRef.trim()) return;
    try {
      await connect.mutateAsync({
        provider,
        body: { display_name: displayName.trim(), credential_ref: credentialRef.trim() },
      });
      setDisplayName("");
      setCredentialRef("");
    } catch {
      // The mutation error is shown alongside the form.
    }
  }

  return (
    <details className="settings-source-control">
      <summary>Repository platform integrations <span className="muted">GitHub, GitLab, Hugging Face and Bitbucket</span></summary>
      <div className="settings-scm-body">
        {items.length > 0 && (
          <div className="settings-scm-list">
            {items.map((connection) => (
              <div key={connection.id} className="settings-scm-row">
                <div><strong>{connection.display_name}</strong> <span className="muted mono">{connection.provider}</span><p className="muted">{connection.account || connection.credential_ref || "Secret reference configured"}</p></div>
                <Pill tone={statusTone(connection.status)}>{connection.status}</Pill>
                <button className="btn" disabled={disconnect.isPending} onClick={() => { if (window.confirm(`Disconnect ${connection.display_name}?`)) disconnect.mutate(connection.id); }}>Disconnect</button>
              </div>
            ))}
          </div>
        )}
        <p className="muted">Repository credentials are managed by reference (environment variable, KMS ARN or Vault path). Never paste a token into the reference field.</p>
        <form onSubmit={submit} className="settings-scm-form">
          <label>Provider
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {SCM_PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label>Display name
            <input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Engineering GitHub" />
          </label>
          <label>Credential reference
            <input required value={credentialRef} onChange={(e) => setCredentialRef(e.target.value)} placeholder="env:GITHUB_PAT" />
          </label>
          <button type="submit" className="btn btn-primary" disabled={connect.isPending}>{connect.isPending ? "Saving…" : "Connect"}</button>
        </form>
        {connect.isError && <p role="alert" className="connector-error">{connect.error?.detail || "The integration could not be saved."}</p>}
        {disconnect.isError && <p role="alert" className="connector-error">{disconnect.error?.detail || "Could not disconnect integration."}</p>}
      </div>
    </details>
  );
}

export function Settings() {
  const me = useSession();
  const integrations = useIntegrations();
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: listConnections,
    retry: 1,
  });
  const legacyItems = (integrations.data?.items || []).filter((item) => !SERVICE_PROVIDERS.has(item.provider));

  return (
    <div className="page-fade settings-page">
      <header className="settings-title">
        <h1>Settings</h1>
        <p className="muted">Manage your workspace, service connections and account.</p>
      </header>

      <section className="settings-account" aria-labelledby="settings-account-title">
        <h2 id="settings-account-title">Workspace account</h2>
        <div className="settings-account-card">
          {me.data ? (
            <>
              <div><span className="settings-account-label">Email</span><strong className="mono">{me.data.user.email}</strong></div>
              <div><span className="settings-account-label">Role</span><strong>{me.data.user.role}</strong></div>
              <div><span className="settings-account-label">Organization</span><strong>{me.data.org.name}</strong></div>
              <div><span className="settings-account-label">Plan</span><strong>{me.data.org.plan}</strong></div>
            </>
          ) : (
            <p className="muted">Sign in to view your workspace account.</p>
          )}
        </div>
      </section>

      <ConnectorHub />

      {(connections.isError || legacyItems.length > 0) && <SourceControlIntegrations items={legacyItems} />}
    </div>
  );
}
