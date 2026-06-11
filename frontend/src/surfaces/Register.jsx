import React from "react";

import { register, resendVerification } from "../api/auth.js";

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

const labelStyle = { display: "block", fontSize: 12, margin: "12px 0 6px" };

export function Register({ onLogin }) {
  const [username, setUsername] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [sent, setSent] = React.useState(null); // { email, delivery }
  const [resendMsg, setResendMsg] = React.useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await register({ username, email, password });
      setSent({ email: res.email || email, delivery: res.delivery });
    } catch (err) {
      setError(String(err?.detail || err?.message || "Could not create account."));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setResendMsg("");
    try {
      await resendVerification(sent.email);
      setResendMsg("Verification email re-sent.");
    } catch {
      setResendMsg("Verification email re-sent.");
    }
  };

  const wrap = (children) => (
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
        {children}
      </div>
    </div>
  );

  if (sent) {
    return wrap(
      <>
        <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 600 }}>
          Check your email
        </h1>
        <p className="muted" style={{ margin: "0 0 18px", fontSize: 13 }}>
          We sent a verification link to <strong>{sent.email}</strong>. Confirm
          your email to activate your SelfRepair account.
        </p>
        {!sent.delivery && (
          <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            Email delivery isn’t configured on this instance — ask an admin to
            verify your account.
          </p>
        )}
        {resendMsg && (
          <p style={{ fontSize: 12, color: "var(--cyan, #4fd1c5)" }}>{resendMsg}</p>
        )}
        <button
          className="btn"
          style={{ width: "100%", marginTop: 8 }}
          onClick={resend}
        >
          Resend verification email
        </button>
        <p className="muted" style={{ margin: "14px 0 0", fontSize: 12, textAlign: "center" }}>
          <button
            type="button"
            onClick={onLogin}
            className="btn btn-ghost"
            style={{ color: "var(--cyan, #4fd1c5)", padding: 0, background: "none", border: "none", cursor: "pointer" }}
          >
            Back to sign in
          </button>
        </p>
      </>,
    );
  }

  return wrap(
    <form onSubmit={submit}>
      <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 600 }}>
        Create your account
      </h1>
      <p className="muted" style={{ margin: "0 0 18px", fontSize: 13 }}>
        SelfRepair Console
      </p>

      <label style={{ ...labelStyle, marginTop: 0 }}>Username</label>
      <input
        autoFocus
        required
        autoComplete="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        style={inputStyle}
      />

      <label style={labelStyle}>Email</label>
      <input
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        style={inputStyle}
      />

      <label style={labelStyle}>Password</label>
      <input
        type="password"
        required
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        style={inputStyle}
      />

      <label style={labelStyle}>Confirm password</label>
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
        {busy ? "Creating account…" : "Create account"}
      </button>

      <p className="muted" style={{ margin: "14px 0 0", fontSize: 12, textAlign: "center" }}>
        Already have an account?{" "}
        <button
          type="button"
          onClick={onLogin}
          style={{ color: "var(--cyan, #4fd1c5)", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 12 }}
        >
          Sign in
        </button>
      </p>
    </form>,
  );
}
