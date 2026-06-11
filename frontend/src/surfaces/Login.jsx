import React from "react";

import { useLogin } from "../hooks/useSession.js";

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

export function Login({ onLoggedIn, onRegister, onForgot, notice, initialEmail }) {
  const [email, setEmail] = React.useState(initialEmail || "");
  const [password, setPassword] = React.useState("");
  const [orgId, setOrgId] = React.useState("");
  const login = useLogin();

  const submit = async (e) => {
    e.preventDefault();
    try {
      await login.mutateAsync({
        email,
        password,
        ...(orgId ? { org_id: orgId } : {}),
      });
      onLoggedIn?.();
    } catch {
      // Surfaced via login.error below; nothing to do here.
    }
  };

  const errorDetail =
    login.isError && (login.error?.detail || login.error?.message);

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
      <form
        onSubmit={submit}
        className="card"
        style={{ width: "min(380px, 100%)", padding: 28 }}
      >
        <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 600 }}>
          Sign in
        </h1>
        <p
          className="muted"
          style={{ margin: "0 0 18px", fontSize: 13 }}
        >
          SelfRepair Console
        </p>

        {notice && (
          <div
            role="status"
            style={{
              background: "rgba(79,209,197,0.12)",
              border: "1px solid rgba(79,209,197,0.35)",
              color: "var(--cyan, #4fd1c5)",
              borderRadius: 6,
              padding: "9px 11px",
              fontSize: 13,
              marginBottom: 14,
            }}
          >
            {notice}
          </div>
        )}

        <label
          style={{ display: "block", fontSize: 12, marginBottom: 6 }}
        >
          Email
        </label>
        <input
          type="email"
          autoFocus
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={inputStyle}
        />

        <label
          style={{
            display: "block",
            fontSize: 12,
            margin: "12px 0 6px",
          }}
        >
          Password
        </label>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={inputStyle}
        />

        <details style={{ marginTop: 12 }}>
          <summary
            className="muted"
            style={{ fontSize: 12, cursor: "pointer" }}
          >
            Multiple organisations? Specify org id
          </summary>
          <input
            type="text"
            value={orgId}
            placeholder="00000000-0000-0000-0000-000000000001"
            onChange={(e) => setOrgId(e.target.value)}
            style={{ ...inputStyle, marginTop: 8 }}
          />
        </details>

        {errorDetail && (
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
            {String(errorDetail)}
          </div>
        )}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={login.isPending}
          style={{ marginTop: 18, width: "100%" }}
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>

        <p
          className="muted"
          style={{ margin: "14px 0 0", fontSize: 12, textAlign: "center" }}
        >
          New here?{" "}
          <button
            type="button"
            onClick={onRegister}
            style={{ color: "var(--cyan, #4fd1c5)", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 12 }}
          >
            Create an account
          </button>
        </p>
        <p
          className="muted"
          style={{ margin: "6px 0 0", fontSize: 12, textAlign: "center" }}
        >
          <button
            type="button"
            onClick={onForgot}
            style={{ color: "var(--cyan, #4fd1c5)", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: 12 }}
          >
            Forgot your password?
          </button>
        </p>
      </form>
    </div>
  );
}
