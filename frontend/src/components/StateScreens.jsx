import React from "react";

// Short, support-friendly request id for an error instance.
function makeRequestId() {
  const rnd = Math.random().toString(36).slice(2, 8).toUpperCase();
  return `REQ-${Date.now().toString(36).toUpperCase()}-${rnd}`;
}

const Brand = () => (
  <div className="state-brand">
    <span className="brandmark">
      <span className="check">
        <svg viewBox="0 0 24 24" fill="none" stroke="#0A0E27" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12.5l4.5 4.5L19 7" />
        </svg>
      </span>
    </span>
    <span>SelfRepair</span>
  </div>
);

const AlertGlyph = () => (
  <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

/** Full-screen loading state — replaces any blank/black render. */
export const LoadingState = ({ label = "Loading your workspace…", full }) => (
  <div className={`state-screen${full ? " full" : ""}`}>
    <Brand />
    <div className="spinner" />
    <div className="state-msg" style={{ marginTop: 14 }}>{label}</div>
  </div>
);

/** Friendly empty state for surfaces with no data yet. */
export const EmptyState = ({ title = "Nothing here yet", message, action }) => (
  <div className="state-screen">
    <div className="state-icon">
      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9h18M8 14h8" />
      </svg>
    </div>
    <div className="state-title">{title}</div>
    {message && <div className="state-msg">{message}</div>}
    {action && <div className="state-actions">{action}</div>}
  </div>
);

/**
 * Enterprise error state with recovery actions + support metadata.
 * Use inside surfaces (inline) or as the crash fallback (full).
 */
export const ErrorState = ({
  code = "MOB-LOAD-001",
  title = "Unable to load this page",
  message = "Something went wrong while loading your workspace. Please try again — if the issue continues, contact support with the details below.",
  requestId,
  onRetry,
  full = false,
}) => {
  const reqId = requestId || makeRequestId();
  const ts = new Date().toISOString();
  const support = `mailto:support@ruslanmv.com?subject=SelfRepair%20error%20${code}&body=Request%20ID:%20${reqId}%0ATime:%20${ts}`;
  return (
    <div className={`state-screen${full ? " full" : ""}`} role="alert">
      {full && <Brand />}
      <div className="state-icon danger"><AlertGlyph /></div>
      <div className="state-title">{title}</div>
      <div className="state-msg">{message}</div>
      <div className="state-actions">
        <button className="btn btn-primary" onClick={onRetry || (() => window.location.reload())}>Retry</button>
        <button className="btn" onClick={() => { window.location.href = "/"; }}>Go back</button>
        <a className="btn btn-ghost" href={support}>Contact support</a>
      </div>
      <div className="state-meta">
        Error code: {code}<br />
        Request ID: {reqId}<br />
        Time: {ts}<br />
        Env: {window.location.host}
      </div>
    </div>
  );
};

/**
 * Top-level error boundary: catches any render/runtime crash and shows the
 * enterprise error screen instead of a blank/black page.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, requestId: null };
  }

  static getDerivedStateFromError() {
    return { hasError: true, requestId: makeRequestId() };
  }

  componentDidCatch(error, info) {
    // Silent technical logging — never surfaced to the user verbatim.
    // eslint-disable-next-line no-console
    console.error("[SelfRepair] UI crash", { error, info, requestId: this.state.requestId });
  }

  handleRetry = () => {
    // Clear the boundary; if the tree still throws, a reload is the fallback.
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        <ErrorState
          full
          code="MOB-APP-500"
          requestId={this.state.requestId}
          title="The console hit an unexpected error"
          message="We’ve logged the issue. You can retry, reload, or sign in again. If it keeps happening, contact support with the request ID below."
          onRetry={this.handleRetry}
        />
      );
    }
    return this.props.children;
  }
}
