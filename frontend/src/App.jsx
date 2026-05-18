import React from "react";

import { Icon } from "./components/atoms.jsx";
import { CommandPalette, Sidebar, Topbar } from "./components/Shell.jsx";
import { ACCENT_MAP, TweaksPanel, useTweaks } from "./components/TweaksPanel.jsx";
import { AuditLogDrawer } from "./features/AuditLogDrawer.jsx";
import { AutoRepairModal } from "./features/AutoRepairModal.jsx";
import { ChatDock, ChatToggle } from "./features/ChatDock.jsx";
import { RunRepairModal } from "./features/RunRepairModal.jsx";
import { useLogout } from "./hooks/useSession.js";
import { AuditLog } from "./surfaces/AuditLog.jsx";
import { Findings } from "./surfaces/Findings.jsx";
import { JobDetail } from "./surfaces/JobDetail.jsx";
import { Jobs } from "./surfaces/Jobs.jsx";
import { Login } from "./surfaces/Login.jsx";
import { OpenIssues } from "./surfaces/OpenIssues.jsx";
import { Overview } from "./surfaces/Overview.jsx";
import { Policies } from "./surfaces/Policies.jsx";
import { RepairDetail } from "./surfaces/RepairDetail.jsx";
import { Repairs } from "./surfaces/Repairs.jsx";
import { RepoDetail } from "./surfaces/RepoDetail.jsx";
import { Repos } from "./surfaces/Repos.jsx";
import { Settings } from "./surfaces/Settings.jsx";
import { StubPage } from "./surfaces/StubPage.jsx";

export default function App() {
  const [tweaks, setTweak] = useTweaks();
  const [route, setRoute] = React.useState({ name: "overview", payload: null });
  const [cmdOpen, setCmdOpen] = React.useState(false);

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

  const navigate = (name, payload = null) => setRoute({ name, payload });

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
    if (route.name === "settings") return [home, { label: "Settings" }];
    if (route.name === "login") return [home, { label: "Sign in" }];
    if (route.name === "about") return [home, { label: "About" }];
    if (route.name === "help") return [home, { label: "Help" }];
    return [home];
  })();

  const sidebarKey =
    {
      overview: "overview",
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
      settings: "settings",
      about: "settings",
      help: "settings",
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
      case "settings":
        return <Settings />;
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

  return (
    <div className="app-shell" data-screen-label={route.name}>
      <Sidebar
        route={sidebarKey}
        onNav={navigate}
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
        <Topbar crumbs={crumbs} onCmd={() => setCmdOpen(true)} right={topbarRight} />
        <div className="content">{renderRoute()}</div>
      </main>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} onPick={onPickCmd} />

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
