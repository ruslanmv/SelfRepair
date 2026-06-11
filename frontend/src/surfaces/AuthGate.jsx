import React from "react";

import { ForgotPassword } from "./ForgotPassword.jsx";
import { Login } from "./Login.jsx";
import { Register } from "./Register.jsx";
import { ResetPassword } from "./ResetPassword.jsx";
import { VerifyEmail } from "./VerifyEmail.jsx";

/**
 * Pre-auth gate. Decides what unauthenticated screen to show:
 *  - If the URL carries a verify token (/verify?token=) -> VerifyEmail.
 *  - If the URL carries a reset token (/reset-password?token=) -> ResetPassword.
 *  - Otherwise cycles login | register | forgot (login default).
 *
 * After consuming a token from the URL it is cleared with history.replaceState
 * so a refresh doesn't reprocess it. On login success the parent's onLoggedIn
 * refetches the session; verify/reset success routes back to Login.
 */
function readTokenView() {
  if (typeof window === "undefined") return null;
  const { pathname, search } = window.location;
  const params = new URLSearchParams(search || "");
  const token = params.get("token") || "";
  if (!token) return null;
  if (pathname.includes("verify")) return { view: "verify", token };
  if (pathname.includes("reset-password")) return { view: "reset", token };
  return null;
}

function clearTokenFromUrl() {
  if (typeof window === "undefined" || !window.history?.replaceState) return;
  // Keep a clean path; drop the ?token= so a refresh can't reprocess it.
  window.history.replaceState({}, "", window.location.pathname);
}

export function AuthGate({ onLoggedIn }) {
  const initialToken = React.useMemo(readTokenView, []);
  const [view, setView] = React.useState(initialToken ? initialToken.view : "login");
  const tokenRef = React.useRef(initialToken ? initialToken.token : "");

  // Once a token view is mounted, strip the token from the URL so a refresh
  // (or a second effect run) doesn't reprocess an already-consumed token.
  React.useEffect(() => {
    if (initialToken) clearTokenFromUrl();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [notice, setNotice] = React.useState(null);
  const goLogin = () => {
    setNotice(null);
    setView("login");
  };
  // Best practice: after a password reset / email verify, send the user to
  // sign in WITH a clear confirmation banner so they never re-use an old
  // password by mistake.
  const goLoginWithNotice = (msg) => {
    setNotice(msg);
    setView("login");
  };

  if (view === "verify") {
    return (
      <VerifyEmail
        token={tokenRef.current}
        onLogin={() => goLoginWithNotice("Your email is verified. Sign in to continue.")}
      />
    );
  }
  if (view === "reset") {
    return (
      <ResetPassword
        token={tokenRef.current}
        onLogin={() => goLoginWithNotice("Your password was updated. Sign in with your new password.")}
      />
    );
  }
  if (view === "register") {
    return <Register onLogin={goLogin} />;
  }
  if (view === "forgot") {
    return <ForgotPassword onLogin={goLogin} />;
  }
  return (
    <Login
      onLoggedIn={onLoggedIn}
      onRegister={() => setView("register")}
      onForgot={() => setView("forgot")}
      notice={notice}
    />
  );
}
