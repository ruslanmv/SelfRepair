import React from "react";

import { Icon } from "./components/atoms.jsx";
import { CommandPalette, Sidebar, Topbar } from "./components/Shell.jsx";
import { ACCENT_MAP, TweaksPanel, useTweaks } from "./components/TweaksPanel.jsx";
import { AuditLogDrawer } from "./features/AuditLogDrawer.jsx";
import { AutoRepairModal } from "./features/AutoRepairModal.jsx";
import { ChatDock, ChatToggle } from "./features/ChatDock.jsx";
import { RunRepairModal } from "./features/RunRepairModal.jsx";
import { useLogout, useSession } from "./hooks/useSession.js";
import { EmptyState, ErrorState, LoadingState } from "./components/StateScreens.jsx";
import { AuditLog } from "./surfaces/AuditLog.jsx";
import { AdminUsers } from "./surfaces/admin/AdminUsers.jsx";
import { AdminSystem } from "./surfaces/admin/AdminSystem.jsx";
import { AdminLogs } from "./surfaces/admin/AdminLogs.jsx";
import { Findings } from "./surfaces/Findings.jsx";
import { Inbox } from "./surfaces/Inbox.jsx";
import { JobDetail } from "./surfaces/JobDetail.jsx";
import { Jobs } from "./surfaces/Jobs.jsx";
import { AuthGate } from "./surfaces/AuthGate.jsx";
import { Login } from "./surfaces/Login.jsx";
import { Connections } from "./surfaces/Connections.jsx";
import { OpenIssues } from "./surfaces/OpenIssues.jsx";
import { Overview } from "./surfaces/Overview.jsx";
import { Policies } from "./surfaces/Policies.jsx";
import { RepairDetail } from "./surfaces/RepairDetail.jsx";
import { Repairs } from "./surfaces/Repairs.jsx";
import { RepoDetail } from "./surfaces/RepoDetail.jsx";
import { Repos } from "./surfaces/Repos.jsx";
import { Settings } from "./surfaces/Settings.jsx";
import { StubPage } from "./surfaces/StubPage.jsx";

function NotAuthorized() {
  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <EmptyState
        title="Not authorized"
        message="This area is restricted to administrators."
      />
    </div>
  );
}

export default function App() {
  const [tweaks, setTweak] = useTweaks();
  const [route, setRoute] = React.useState({ name: "overview", payload: null });
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const [navOpen, setNavOpen] = React.useState(false);

  const session = useSession();

  const [runOpen, setRunOpen] = React.useState(false);
  const [runTarget, setRunTarget] = React.useState(null);
  const [auditOpen, setAuditOpen] = React.useState(false);
  const [auditScope, setAuditScope] = React.useState({ scope: "job", scopeId: "" });
  const [chatOpen, setChatOpen] = React.useState(false);
  const [autoOpen, setAutoOpen] = React.useState(false);
  const [autoActive, setAutoActive] = React.useState(false);
  const [autoCount, setAutoCount] = React.useState(0);

  const logoutMutation = useLogout();

  React.useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", tweaks.theme);
    root.setAttribute("data-density", tweaks.density);
    const a = ACCENT_MAP[tweaks.accent] || ACCENT_MAP.violet;
    root.style.setProperty("--brand", a.brand);
    root.style.setProperty("--brand-2", a.brand2);
    root.style.setProperty("--grad-brand", a.grad);
  }, [tweaks]);

  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const navigate = (name, payload = null) => {
    setRoute({ name, payload });
    setNavOpen(false); // close the mobile drawer on any navigation
  };

  // Real signed-in user for the sidebar/account menu (no placeholder identity).
  const sUser = session.data?.user;
  const isAdmin = (sUser?.role || "user") === "admin";
  const currentUser = sUser
    ? {
        name: sUser.display_name || sUser.name || sUser.username || sUser.email || "User",
        email: sUser.email || "",
        initials:
          (sUser.display_name || sUser.username || sUser.email || "S R")
            .split(/[\s@._-]+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((p) => p[0].toUpperCase())
            .join("") || "SR",
        hue: 200,
      }
    : undefined;

  const openRun = (target) => {
    setRunTarget(target);
    setRunOpen(true);
  };
  const openAudit = (scope, scopeId) => {
    setAuditScope({ scope, scopeId });
    setAuditOpen(true);
  };

  const onPickCmd = (item) => {
    if (!item.route) return;
    navigate(item.route, item.payload);
  };

  const shortId = (s) =>
    typeof s === "string" && s.length > 8 ? s.slice(0, 8) : s || "";

  const crumbs = (() => {
    const home = { label: "Fleet", onClick: () => navigate("overview") };
    if (route.name === "overview") return [home, { label: "Overview" }];
    if (route.name === "inbox") return [home, { label: "Inbox" }];
    if (route.name === "repos") return [home, { label: "Repos" }];
    if (route.name === "repo")
      return [
        home,
        { label: "Repos", onClick: () => navigate("repos") },
        { label: shortId(route.payload) || "Repo" },
      ];
    if (route.name === "findings") return [home, { label: "Findings" }];
    if (route.name === "issues") return [home, { label: "Open Issues" }];
    if (route.name === "repairs") return [home, { label: "Repairs" }];
    if (route.name === "repair")
      return [
        home,
        { label: "Repairs", onClick: () => navigate("repairs") },
        { label: shortId(route.payload) || "Repair" },
      ];
    if (route.name === "jobs") return [home, { label: "Jobs" }];
    if (route.name === "job")
      return [
        home,
        { label: "Jobs", onClick: () => navigate("jobs") },
        { label: shortId(route.payload) || "Job" },
      ];
    if (route.name === "policies") return [home, { label: "Policies" }];
    if (route.name === "audit") return [home, { label: "Audit log" }];
    if (route.name === "connections") return [home, { label: "Connections" }];
    if (route.name === "settings") return [home, { label: "Settings" }];
    if (route.name === "admin-users") return [home, { label: "Admin" }, { label: "Users" }];
    if (route.name === "admin-system") return [home, { label: "Admin" }, { label: "System" }];
    if (route.name === "admin-logs") return [home, { label: "Admin" }, { label: "Logs" }];
    if (route.name === "login") return [home, { label: "Sign in" }];
    if (route.name === "about") return [home, { label: "About" }];
    if (route.name === "help") return [home, { label: "Help" }];
    return [home];
  })();

  const sidebarKey =
    {
      overview: "overview",
      inbox: "inbox",
      repos: "repos",
      repo: "repos",
      findings: "findings",
      issues: "issues",
      repairs: "repairs",
      repair: "repairs",
      jobs: "jobs",
      job: "jobs",
      policies: "policies",
      audit: "audit",
      connections: "connections",
      settings: "settings",
      about: "settings",
      help: "settings",
      "admin-users": "admin-users",
      "admin-system": "admin-system",
      "admin-logs": "admin-logs",
    }[route.name] || "overview";

  const chatScope = (() => {
    if (route.name === "findings") return { scope: "findings", label: "Findings" };
    if (route.name === "issues") return { scope: "issues", label: "Open Issues" };
    if (route.name === "repair" || route.name === "repairs")
      return {
        scope: "repairs",
        label: route.name === "repair" ? `Repair ${shortId(route.payload)}` : "Repairs queue",
      };
    if (route.name === "job" || route.name === "jobs")
      return {
        scope: "jobs",
        label: route.name === "job" ? `Job ${shortId(route.payload)}` : "Jobs",
      };
    if (route.name === "repo")
      return {
        scope: "default",
        label: shortId(route.payload) || "Repo",
      };
    return { scope: "default", label: "Fleet" };
  })();

  React.useEffect(() => {
    if (tweaks.chatScopedToPage) setChatOpen(false);
  }, [route.name, tweaks.chatScopedToPage]);

  const renderRoute = () => {
    switch (route.name) {
      case "overview":
        return <Overview onNav={navigate} showHeroGradient={tweaks.showHeroGradient} />;
      case "inbox":
        return <Inbox onNav={navigate} />;
      case "repos":
        return <Repos onNav={navigate} layout={tweaks.reposLayout} />;
      case "repo":
        return (
          <RepoDetail
            repoId={route.payload}
            onNav={navigate}
            onOpenAudit={openAudit}
            onOpenRun={openRun}
          />
        );
      case "findings":
        return <Findings onNav={navigate} />;
      case "issues":
        return (
          <OpenIssues
            onNav={navigate}
            onOpenRun={openRun}
            onOpenAudit={openAudit}
          />
        );
      case "repairs":
        return <Repairs onNav={navigate} />;
      case "repair":
        return (
          <RepairDetail
            repairId={route.payload}
            onNav={navigate}
            onOpenAudit={openAudit}
          />
        );
      case "jobs":
        return <Jobs onNav={navigate} />;
      case "job":
        return (
          <JobDetail
            jobId={route.payload}
            onNav={navigate}
            onOpenAudit={openAudit}
          />
        );
      case "policies":
        return <Policies />;
      case "audit":
        return <AuditLog />;
      case "connections":
        return <Connections />;
      case "settings":
        return <Settings />;
      case "admin-users":
        return isAdmin ? <AdminUsers /> : <NotAuthorized />;
      case "admin-system":
        return isAdmin ? <AdminSystem /> : <NotAuthorized />;
      case "admin-logs":
        return isAdmin ? <AdminLogs /> : <NotAuthorized />;
      case "login":
        return <Login onLoggedIn={() => navigate("overview")} />;
      case "about":
        return (
          <StubPage
            title="About SelfRepair"
            subtitle="AI Secure Delivery Copilot · v1.0 · Apache-2.0"
          />
        );
      case "help":
        return (
          <StubPage
            title="Help & Documentation"
            subtitle="Quick start · API reference · operator runbooks"
          />
        );
      default:
        return <Overview onNav={navigate} showHeroGradient={tweaks.showHeroGradient} />;
    }
  };

  const topbarRight = (
    <>
      {autoActive && (
        <span className="pill pill-info" title={`${autoCount} repos under continuous auto-repair`}>
          <span
            className="pill-dot"
            style={{ background: "var(--cyan)", animation: "pulse 1.6s infinite" }}
          />
          auto-repair · {autoCount}
        </span>
      )}
      <button
        className="btn"
        onClick={() => setAutoOpen(true)}
        title="Configure auto-repair across selected repos"
      >
        <Icon name="settings" s={13} /> Auto-repair
      </button>
      <button
        className="btn btn-primary"
        onClick={() => {
          setRunTarget(null);
          setRunOpen(true);
        }}
        title="Run a one-shot repair"
      >
        <Icon name="play" s={12} /> Run repair
      </button>
      <ChatToggle active={chatOpen} onClick={() => setChatOpen((o) => !o)} />
    </>
  );

  // Never render a blank/black screen: show explicit loading, then gate on auth.
  if (session.isLoading) {
    return <LoadingState full />;
  }
  if (!sUser) {
    // Distinguish "logged out" (show sign in) from "backend briefly
    // unreachable" (show a friendly retry) — a transient 5xx / network error
    // while the Space wakes up must never look like a crash.
    const status = session.error?.status;
    if (session.isError && status !== 401) {
      return (
        <ErrorState
          full
          code="MOB-AUTH-503"
          title="Can’t reach SelfRepair right now"
          message="We couldn’t load your session — this is usually temporary while the service wakes up. Please retry in a moment."
          onRetry={() => session.refetch()}
        />
      );
    }
    // Not authenticated (or session expired) -> full-screen auth gate
    // (sign in / register / forgot / verify / reset, all in the console design).
    return (
      <AuthGate
        onLoggedIn={() => {
          navigate("overview");
          session.refetch();
        }}
      />
    );
  }

  return (
    <div
      className={`app-shell${navOpen ? " nav-open" : ""}`}
      data-screen-label={route.name}
    >
      <div className="nav-backdrop" onClick={() => setNavOpen(false)} />
      <Sidebar
        route={sidebarKey}
        onNav={navigate}
        user={currentUser}
        isAdmin={isAdmin}
        onClose={() => setNavOpen(false)}
        workspace={session.data?.org?.name || "agent-matrix"}
        onAccountAction={async (action) => {
          if (action === "settings") navigate("settings");
          else if (action === "about") navigate("about");
          else if (action === "help") navigate("help");
          else if (action === "logout") {
            if (window.confirm("Sign out of the SelfRepair console?")) {
              try {
                await logoutMutation.mutateAsync();
              } catch {
                // Best-effort; cookie/network glitches shouldn't block the UI.
              }
              navigate("login");
            }
          }
        }}
      />
      <main className="main">
        <Topbar
          crumbs={crumbs}
          onCmd={() => setCmdOpen(true)}
          onMenu={() => setNavOpen(true)}
          right={topbarRight}
          onNav={navigate}
        />
        <div className="content">{renderRoute()}</div>
      </main>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} onPick={onPickCmd} isAdmin={isAdmin} />

      <RunRepairModal
        open={runOpen}
        onClose={() => setRunOpen(false)}
        onNav={navigate}
        defaultRepo={runTarget}
      />

      <AuditLogDrawer
        open={auditOpen}
        onClose={() => setAuditOpen(false)}
        scope={auditScope.scope}
        scopeId={auditScope.scopeId}
      />

      <AutoRepairModal
        open={autoOpen}
        onClose={() => setAutoOpen(false)}
        onLaunch={({ repos }) => {
          setAutoActive(true);
          setAutoCount(repos.length);
        }}
      />

      <ChatDock
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        scope={chatScope.scope}
        scopeLabel={chatScope.label}
      />

      <TweaksPanel values={tweaks} setTweak={setTweak} />
    </div>
  );
}
