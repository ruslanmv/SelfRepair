import React from "react";

import { resendVerification, verifyEmail } from "../api/auth.js";

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

export function VerifyEmail({ token, onLogin }) {
  const [state, setState] = React.useState("checking"); // checking | ok | invalid
  const [email, setEmail] = React.useState("");
  const [resendMsg, setResendMsg] = React.useState("");

  React.useEffect(() => {
    let active = true;
    (async () => {
      try {
        await verifyEmail(token);
        if (active) setState("ok");
      } catch {
        if (active) setState("invalid");
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  // After a successful verification, auto-redirect to sign in shortly after
  // the confirmation (best practice: clear outcome + a path forward).
  React.useEffect(() => {
    if (state !== "ok") return undefined;
    const t = setTimeout(() => onLogin?.(), 2500);
    return () => clearTimeout(t);
  }, [state, onLogin]);

  const resend = async (e) => {
    e.preventDefault();
    setResendMsg("");
    try {
      await resendVerification(email);
    } catch {
      // Neutral.
    }
    setResendMsg("If that account exists and is unverified, a new link is on its way.");
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
          Email verification
        </h1>
        <p className="muted" style={{ margin: "0 0 18px", fontSize: 13 }}>
          SelfRepair Console
        </p>

        {state === "checking" && (
          <p className="muted" style={{ fontSize: 13 }}>Verifying your email…</p>
        )}

        {state === "ok" && (
          <>
            <p style={{ fontSize: 13, color: "var(--cyan, #4fd1c5)" }}>
              Your email is verified.
            </p>
            <p className="muted" style={{ fontSize: 13, marginTop: 6 }}>
              Redirecting you to sign in…
            </p>
            <button
              className="btn btn-primary"
              style={{ width: "100%", marginTop: 18 }}
              onClick={onLogin}
            >
              Sign in now
            </button>
          </>
        )}

        {state === "invalid" && (
          <form onSubmit={resend}>
            <p className="muted" style={{ fontSize: 13 }}>
              This verification link is invalid or has expired. Enter your email
              to request a new one.
            </p>
            <label style={{ display: "block", fontSize: 12, margin: "14px 0 6px" }}>
              Email
            </label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
            />
            {resendMsg && (
              <p style={{ fontSize: 12, color: "var(--cyan, #4fd1c5)", marginTop: 10 }}>
                {resendMsg}
              </p>
            )}
            <button type="submit" className="btn btn-primary" style={{ width: "100%", marginTop: 18 }}>
              Resend verification email
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
