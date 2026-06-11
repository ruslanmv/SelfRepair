import React from "react";

import { forgotPassword } from "../api/auth.js";

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

export function ForgotPassword({ onLogin }) {
  const [email, setEmail] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [sent, setSent] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await forgotPassword(email);
    } catch {
      // Neutral by design — always show the same confirmation.
    } finally {
      setBusy(false);
      setSent(true);
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
          Reset your password
        </h1>
        <p className="muted" style={{ margin: "0 0 18px", fontSize: 13 }}>
          SelfRepair Console
        </p>

        {sent ? (
          <>
            <p className="muted" style={{ fontSize: 13 }}>
              If an account exists for that email, a reset link is on its way.
              Check your inbox and follow the link to set a new password.
            </p>
            <button
              className="btn btn-primary"
              style={{ width: "100%", marginTop: 18 }}
              onClick={onLogin}
            >
              Back to sign in
            </button>
          </>
        ) : (
          <form onSubmit={submit}>
            <label style={{ display: "block", fontSize: 12, marginBottom: 6 }}>
              Email
            </label>
            <input
              type="email"
              autoFocus
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={busy}
              style={{ marginTop: 18, width: "100%" }}
            >
              {busy ? "Sending…" : "Send reset link"}
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
