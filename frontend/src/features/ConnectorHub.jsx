import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Icon, Pill } from "../components/atoms.jsx";
import {
  disconnectConnection,
  listConnections,
  pairOllaBridge,
  saveConnection,
  testConnection,
} from "../api/connections.js";

const CLOUD_URL = "https://app.ollabridge.com";
const CLOUD_API_URL = `${CLOUD_URL}/v1`;

const PROVIDERS = [
  {
    id: "ollabridge",
    label: "OllaBridge Cloud",
    initials: "O",
    category: "AI gateway",
    description: "Access private and cloud AI models through one secure gateway.",
    hint: "Choose device pairing for cloud access, or use an existing API key.",
    defaultUrl: CLOUD_API_URL,
  },
  {
    id: "gitpilot",
    label: "GitPilot",
    initials: "G",
    category: "Code generation",
    description: "Send approved repair plans to your coding agent.",
    hint: "Enter your GitPilot service endpoint and its access token, if required.",
    defaultUrl: "https://ruslanmv-gitpilot.hf.space",
  },
  {
    id: "matrixlab",
    label: "MatrixLab",
    initials: "M",
    category: "Sandbox validation",
    description: "Verify patches in isolated execution environments.",
    hint: "Enter your MatrixLab service endpoint and its access token, if required.",
    defaultUrl: "https://ruslanmv-matrixlab.hf.space",
  },
];

const BY_ID = Object.fromEntries(PROVIDERS.map((p) => [p.id, p]));

function errorMessage(error) {
  const detail = error?.detail;
  if (typeof detail === "string") return detail;
  return "The request failed. Check the settings and try again.";
}

function statusLabel(conn) {
  if (conn?.display_status) return conn.display_status;
  if (!conn) return "Not configured";
  if (conn.status === "ok") return conn.has_secret ? "Connected" : "Reachable";
  if (conn.status === "reachable") return "Reachable";
  if (conn.status === "expired") return "Expired";
  if (conn.status === "disconnected") return "Disconnected";
  if (conn.status === "error") return "Needs attention";
  return conn.has_secret ? "Not verified" : "Not configured";
}

function statusTone(conn) {
  const label = statusLabel(conn);
  if (label === "Connected") return "ok";
  if (label === "Reachable" || label === "Pairing") return "info";
  if (label === "Needs attention" || label === "Expired") return "danger";
  return "neutral";
}

function formatWhen(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function cleanCode(value) {
  const raw = value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  return raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
}

function isValidUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname));
  } catch {
    return false;
  }
}

async function copyText(value, setCopied) {
  try {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  } catch {
    setCopied(false);
  }
}

function ConnectorWizard({ initialProvider, connections, onClose, onChanged }) {
  const [providerId, setProviderId] = React.useState(initialProvider);
  const [step, setStep] = React.useState(initialProvider ? 1 : 0);
  const [method, setMethod] = React.useState("pair");
  const [pairCode, setPairCode] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState(() => connections.find((c) => c.provider === initialProvider)?.base_url || BY_ID[initialProvider]?.defaultUrl || "");
  const [apiKey, setApiKey] = React.useState("");
  const [revealKey, setRevealKey] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [result, setResult] = React.useState(null);
  const [requestError, setRequestError] = React.useState("");
  const dialogRef = React.useRef(null);
  const qc = useQueryClient();
  const provider = BY_ID[providerId];
  const existing = connections.find((c) => c.provider === providerId);

  React.useEffect(() => {
    const previouslyFocused = document.activeElement;
    const dialog = dialogRef.current;
    dialog?.focus();
    function handleKey(event) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialog) return;
      const targets = [...dialog.querySelectorAll("a[href],button:not([disabled]),input:not([disabled])")];
      if (!targets.length) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previouslyFocused?.focus?.();
    };
  }, [onClose]);

  const save = useMutation({
    mutationFn: ({ id, body }) => saveConnection(id, body),
  });
  const pair = useMutation({ mutationFn: (code) => pairOllaBridge(code) });
  const busy = save.isPending || pair.isPending;

  function choose(id) {
    const previous = connections.find((c) => c.provider === id);
    setBaseUrl(previous?.base_url || BY_ID[id].defaultUrl);
    setPairCode("");
    setApiKey("");
    setMethod(id === "ollabridge" ? "pair" : "key");
    setRequestError("");
    setResult(null);
    setProviderId(id);
    setStep(1);
  }

  async function submit(event) {
    event.preventDefault();
    setRequestError("");
    try {
      let response;
      if (providerId === "ollabridge" && method === "pair") {
        response = await pair.mutateAsync(cleanCode(pairCode));
      } else {
        const url = baseUrl.trim().replace(/\/+$/, "");
        if (!isValidUrl(url)) {
          setRequestError("Use an HTTPS URL (or localhost for local development).");
          return;
        }
        response = await save.mutateAsync({
          id: providerId,
          body: { base_url: url, ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}) },
        });
      }
      setApiKey("");
      setPairCode("");
      setResult({ ...response, credential_updated: Boolean(apiKey.trim()) });
      setStep(2);
      await qc.invalidateQueries({ queryKey: ["connections"] });
      await qc.invalidateQueries({ queryKey: ["integrations"] });
      onChanged?.();
    } catch (error) {
      setRequestError(errorMessage(error));
    }
  }

  const paired = result?.pairing === "paired";
  const verified = result?.status === "ok";
  const reachable = result?.status === "reachable";
  const resultTitle = verified
    ? paired ? "Device paired and model access verified" : "Access verified"
    : reachable
      ? "Service is reachable"
      : paired ? "Paired, but access needs attention" : "Connection check needs attention";
  const resultTone = verified ? "is-ok" : reachable ? "is-warn" : "is-error";

  return (
    <div className="connector-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="connector-dialog" role="dialog" aria-modal="true" aria-labelledby="connector-dialog-title" tabIndex={-1} ref={dialogRef}>
        <header className="connector-dialog-head">
          <div>
            <div className="connector-eyebrow">CONNECTOR SETUP</div>
            <h2 id="connector-dialog-title">{provider ? `Set up ${provider.label}` : "Add a connector"}</h2>
            <p className="muted">Configure, verify, and manage access in one place.</p>
          </div>
          <button className="connector-icon-btn" onClick={onClose} aria-label="Close setup">×</button>
        </header>
        <nav className="connector-steps" aria-label="Setup progress">
          {["Choose provider", "Configure", "Verify"].map((label, i) => (
            <div className={`connector-step ${i === step ? "is-current" : i < step ? "is-complete" : ""}`} aria-current={i === step ? "step" : undefined} key={label}>
              <span className="connector-step-number">{i < step ? "✓" : i + 1}</span>
              <span>{label}</span>
            </div>
          ))}
        </nav>

        {step === 0 && (
          <div className="connector-dialog-body">
            <p className="connector-section-label">Select the service you want to connect</p>
            <div className="connector-choices">
              {PROVIDERS.map((p) => {
                const c = connections.find((item) => item.provider === p.id);
                return (
                  <button key={p.id} className="connector-choice" onClick={() => choose(p.id)}>
                    <span className={`connector-logo connector-logo-${p.id}`}>{p.initials}</span>
                    <span className="connector-choice-text">
                      <strong>{p.label}</strong>
                      <small>{p.description}</small>
                    </span>
                    <span className="connector-choice-end">
                      {["Connected", "Reachable", "Needs attention", "Expired"].includes(statusLabel(c)) && (
                        <span className="connector-existing">{statusLabel(c)}</span>
                      )}
                      <Icon name="caret" s={17} />
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {step === 1 && provider && (
          <form onSubmit={submit}>
            <div className="connector-dialog-body">
              <div className="connector-provider-heading">
                <span className={`connector-logo connector-logo-${provider.id}`}>{provider.initials}</span>
                <div><strong>{provider.label}</strong><p className="muted">{provider.hint}</p></div>
              </div>
              {provider.id === "ollabridge" && (
                <div className="connector-methods" role="group" aria-label="Connection method">
                  <button type="button" className={method === "pair" ? "is-active" : ""} onClick={() => { setMethod("pair"); setRequestError(""); }}>
                    <Icon name="shield" s={15} /> Device pairing
                  </button>
                  <button type="button" className={method === "key" ? "is-active" : ""} onClick={() => { setMethod("key"); setRequestError(""); }}>
                    <Icon name="settings" s={15} /> API key
                  </button>
                </div>
              )}
              {provider.id === "ollabridge" && method === "pair" ? (
                <div className="connector-pairing">
                  <div className="connector-pair-instruction">
                    <span className="connector-instruction-index">1</span>
                    <div>
                      <strong>Generate a code while signed in</strong>
                      <p>Open OllaBridge Cloud, choose <b>Device pairing</b>, and copy the short-lived code. SelfRepair does not create codes. A code that is not linked to your signed-in account is rejected.</p>
                      <a className="connector-open-link" href={CLOUD_URL} target="_blank" rel="noreferrer">
                        Open OllaBridge dashboard <Icon name="external" s={14} />
                      </a>
                    </div>
                  </div>
                  <div className="connector-pair-instruction">
                    <span className="connector-instruction-index">2</span>
                    <div className="connector-grow">
                      <strong>Enter your pairing code</strong>
                      <p>The code appears in OllaBridge, not in SelfRepair. It is exchanged securely by the SelfRepair server.</p>
                      <label className="connector-field-label" htmlFor="connector-pair-code">Pairing code</label>
                      <input id="connector-pair-code" className="connector-input connector-code-input" value={pairCode} onChange={(e) => setPairCode(cleanCode(e.target.value))} autoComplete="one-time-code" maxLength={9} placeholder="ABCD-1234" required aria-describedby="connector-code-help" autoFocus />
                      <small id="connector-code-help" className="muted">8 letters or digits. Expired codes must be regenerated in OllaBridge.</small>
                    </div>
                  </div>
                  <div className="connector-server-block">
                    <div><span className="connector-field-label">OllaBridge server URL</span><code>{CLOUD_URL}</code><small className="muted">For the Base URL field of other apps.</small></div>
                    <button type="button" className="btn" onClick={() => copyText(CLOUD_URL, setCopied)}>{copied ? "Copied" : "Copy URL"}</button>
                  </div>
                </div>
              ) : (
                <div className="connector-fields">
                  <label className="connector-field-label" htmlFor="connector-base-url">Base URL</label>
                  <input id="connector-base-url" className="connector-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={provider.defaultUrl} type="url" required />
                  <small className="muted">Use the service root URL{provider.id === "ollabridge" ? " including /v1" : ""}. HTTPS is recommended.</small>
                  <label className="connector-field-label connector-field-gap" htmlFor="connector-key">{provider.id === "ollabridge" ? "API key / device token" : "Service access token (optional)"}</label>
                  <div className="connector-secret-field">
                    <input id="connector-key" className="connector-input" type={revealKey ? "text" : "password"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="new-password" placeholder={existing?.has_secret ? "Leave blank to retain saved token" : "Paste a token if required"} />
                    <button type="button" onClick={() => setRevealKey((v) => !v)} aria-label={revealKey ? "Hide token" : "Show token"}>{revealKey ? "Hide" : "Show"}</button>
                  </div>
                  {existing?.has_secret && <small className="muted">A token is already saved securely. You do not need to re-enter it.</small>}
                  <p className="connector-safety"><Icon name="shield" s={15} /> Tokens are encrypted on the server and never returned by the API.</p>
                </div>
              )}
              {requestError && <p className="connector-error" role="alert">{requestError}</p>}
            </div>
            <footer className="connector-dialog-foot">
              <button type="button" className="btn" onClick={() => { if (!initialProvider) { setStep(0); setProviderId(null); } else onClose(); }}>{initialProvider ? "Cancel" : "Back"}</button>
              <button type="submit" className="btn btn-primary" disabled={busy || (providerId === "ollabridge" && method === "pair" ? cleanCode(pairCode).length !== 9 : !baseUrl.trim())}>
                {busy ? "Checking connection…" : providerId === "ollabridge" && method === "pair" ? "Pair & verify" : "Save & test"}
              </button>
            </footer>
          </form>
        )}

        {step === 2 && provider && (
          <>
            <div className="connector-dialog-body">
              <div className={`connector-result ${resultTone}`} role="status">
                <span className="connector-result-icon"><Icon name={verified || reachable ? "check" : "shield"} s={27} /></span>
                <h3>{resultTitle}</h3>
                <p>{result?.detail || "The service could not be verified. Check the connection settings and try again."}</p>
                {result?.workflow_verified === false && (
                  <p className="connector-result-note">This check did not run a repair or a sandbox job.</p>
                )}
              </div>
              <div className="connector-result-summary">
                <span>Provider</span><strong>{provider.label}</strong>
                <span>Server</span><code>{paired ? CLOUD_API_URL : baseUrl}</code>
                <span>Credential</span><strong>{paired ? "Device token securely saved" : result?.credential_updated ? "Updated" : existing?.has_secret ? "Existing token retained" : "Not provided"}</strong>
              </div>
              {!verified && !reachable && <p className="muted connector-result-note">The settings were saved when a credential was accepted. You can edit them or retry the check.</p>}
            </div>
            <footer className="connector-dialog-foot">
              <button className="btn" onClick={() => { setStep(1); setResult(null); }}>Edit settings</button>
              {!verified && (
                <button className="btn" type="button" onClick={() => { setStep(1); setResult(null); setRequestError(""); }}>Retry</button>
              )}
              <button className="btn btn-primary" onClick={onClose}>{verified || reachable ? "Finish" : "Close"}</button>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}

export function ConnectorHub() {
  const qc = useQueryClient();
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: listConnections,
    retry: 1,
  });
  const [wizardProvider, setWizardProvider] = React.useState(undefined);
  const closeWizard = React.useCallback(() => setWizardProvider(undefined), []);
  const [confirmProvider, setConfirmProvider] = React.useState(null);
  const [notice, setNotice] = React.useState("");
  const test = useMutation({
    mutationFn: testConnection,
    onSuccess: (result, provider) => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: ["integrations"] });
      setNotice(`${BY_ID[provider]?.label || provider}: ${result.detail || result.status}`);
    },
    onError: (error) => setNotice(errorMessage(error)),
  });
  const disconnect = useMutation({
    mutationFn: disconnectConnection,
    onSuccess: (_, provider) => {
      setConfirmProvider(null);
      setNotice(`${BY_ID[provider]?.label || provider} credentials removed.`);
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: ["integrations"] });
    },
    onError: (error) => setNotice(errorMessage(error)),
  });
  const rows = Array.isArray(connections.data) ? connections.data : [];
  const connectedCount = rows.filter((c) => statusLabel(c) === "Connected").length;
  const reachableCount = rows.filter((c) => statusLabel(c) === "Reachable").length;

  return (
    <section className="connector-hub" aria-labelledby="connector-hub-title">
      <div className="connector-hub-head">
        <div>
          <div className="connector-eyebrow">WORKSPACE SERVICES</div>
          <h2 id="connector-hub-title">Connected services</h2>
          <p className="muted">Connect your AI gateway, coding agent, and validation sandbox.</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setNotice(""); setWizardProvider(null); }}>
          <Icon name="plus" s={16} /> Add connector
        </button>
      </div>
      <div className="connector-summary">
        <span><span className="connector-summary-dot" /> {connectedCount} connected · {reachableCount} reachable</span>
        <span>Checks show the last attempt. A health response is not a completed repair.</span>
      </div>
      {connections.isLoading && <p className="muted" role="status">Loading connectors…</p>}
      {connections.isError && (
        <div className="connector-error" role="alert">
          Could not load service connections. This deployment may not expose the connector API.
          <button type="button" className="btn" onClick={() => connections.refetch()}>Retry</button>
        </div>
      )}
      {!connections.isError && (
        <div className="connector-card-grid">
          {PROVIDERS.map((p) => {
            const conn = rows.find((c) => c.provider === p.id);
            return (
              <article className="connector-card" key={p.id}>
                <div className="connector-card-top">
                  <span className={`connector-logo connector-logo-${p.id}`}>{p.initials}</span>
                  <Pill tone={statusTone(conn)} dot>{statusLabel(conn)}</Pill>
                </div>
                <div className="connector-card-type">{p.category}</div>
                <h3>{p.label}</h3>
                <p className="connector-card-description">{p.description}</p>
                <div className="connector-card-endpoint" title={conn?.base_url || p.defaultUrl}>
                  <span>Endpoint</span><code>{conn?.base_url || p.defaultUrl}</code>
                </div>
                {conn?.detail && <p className="connector-card-detail">{conn.detail}</p>}
                {(conn?.last_checked_at || conn?.last_attempted_at) && (
                  <p className="connector-card-meta">
                    {conn.last_checked_at ? `Last success ${formatWhen(conn.last_checked_at)}` : "No successful check yet"}
                    {conn.last_attempted_at ? ` · Last attempt ${formatWhen(conn.last_attempted_at)}` : ""}
                  </p>
                )}
                <div className="connector-card-actions">
                  <button className="btn btn-primary" onClick={() => { setNotice(""); setWizardProvider(p.id); }}>
                    <Icon name="settings" s={14} /> {conn?.has_secret || conn?.last_checked_at ? "Manage" : "Configure"}
                  </button>
                  <button className="btn" disabled={test.isPending || !conn} onClick={() => { setNotice(""); test.mutate(p.id); }} aria-label={`Test ${p.label}`}>
                    <Icon name="retry" s={14} /> Test
                  </button>
                  {conn?.has_secret && <button className="connector-remove" onClick={() => setConfirmProvider(p.id)}>Disconnect</button>}
                </div>
              </article>
            );
          })}
        </div>
      )}
      {notice && <p className="connector-notice" role="status">{notice}</p>}
      <p className="connector-footnote"><Icon name="shield" s={14} /> Credentials are stored encrypted on the server. You can replace or remove them at any time.</p>

      {wizardProvider !== undefined && (
        <ConnectorWizard key={wizardProvider || "choose"} initialProvider={wizardProvider} connections={rows} onChanged={() => setNotice("")} onClose={closeWizard} />
      )}
      {confirmProvider && (
        <div className="connector-overlay">
          <section className="connector-confirm" role="alertdialog" aria-modal="true" aria-labelledby="disconnect-title" aria-describedby="disconnect-desc">
            <h3 id="disconnect-title">Disconnect {BY_ID[confirmProvider]?.label}?</h3>
            <p id="disconnect-desc">This removes the saved token and resets the connection. You can configure it again later.</p>
            <div className="connector-confirm-actions">
              <button className="btn" autoFocus onClick={() => setConfirmProvider(null)} disabled={disconnect.isPending}>Cancel</button>
              <button className="btn connector-danger-btn" onClick={() => disconnect.mutate(confirmProvider)} disabled={disconnect.isPending}>{disconnect.isPending ? "Disconnecting…" : "Disconnect"}</button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
