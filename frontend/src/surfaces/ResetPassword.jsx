import React from "react";

import { resetPassword } from "../api/auth.js";

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

export function ResetPassword({ token, onLogin }) {
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState(false);

  // On success, auto-redirect to sign in shortly after the confirmation, so
  // the user lands on the login screen with their new password fresh in mind.
  React.useEffect(() => {
    if (!done) return undefined;
    const t = setTimeout(() => onLogin?.(), 2500);
    return () => clearTimeout(t);
  }, [done, onLogin]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(String(err?.detail || err?.message || "Could not reset password."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="page-fade"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 16px",
        minHeight: "100vh",
      }}
    >
      <div className="card" style={{ width: "min(380px, 100%)", padding: 28 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 600 }}>
          Set a new password
        </h1>
        <p className="muted" style={{ margin: "0 0 18px", fontSize: 13 }}>
          SelfRepair Console
        </p>

        {done ? (
          <>
            <p style={{ fontSize: 13, color: "var(--cyan, #4fd1c5)" }}>
              Your password has been updated.
            </p>
            <p className="muted" style={{ fontSize: 13, marginTop: 6 }}>
              Redirecting you to sign in — use your new password.
            </p>
            <button
              className="btn btn-primary"
              style={{ width: "100%", marginTop: 18 }}
              onClick={onLogin}
            >
              Go to sign in now
            </button>
          </>
        ) : (
          <form onSubmit={submit}>
            <label style={{ display: "block", fontSize: 12, marginBottom: 6 }}>
              New password
            </label>
            <input
              type="password"
              autoFocus
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
            />
            <label style={{ display: "block", fontSize: 12, margin: "12px 0 6px" }}>
              Confirm new password
            </label>
            <input
              type="password"
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              style={inputStyle}
            />

            {error && (
              <div
                role="alert"
                style={{
                  marginTop: 14,
                  padding: "8px 10px",
                  borderRadius: 6,
                  background: "rgba(220, 50, 70, 0.12)",
                  color: "var(--danger, #f06d75)",
                  fontSize: 13,
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={busy}
              style={{ marginTop: 18, width: "100%" }}
            >
              {busy ? "Updating…" : "Update password"}
            </button>
            <p className="muted" style={{ margin: "14px 0 0", fontSize: 12, textAlign: "center" }}>
              <button
                type="button"
                onClick={onLogin}
                style={{ color: "var(--cyan, #4fd1c5)", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 12 }}
              >
                Back to sign in
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
