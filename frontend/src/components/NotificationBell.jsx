import React from "react";

import { Icon } from "./atoms.jsx";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "../hooks/useNotifications.js";

function relativeTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return d.toLocaleDateString();
}

const KIND_TONE = {
  request_received: "info",
  report_ready: "ok",
  action_needed: "warn",
};

export const NotificationBell = ({ onNav }) => {
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef(null);

  const { data } = useNotifications();
  const items = data?.items || [];
  const unread = data?.unread_count || 0;

  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  React.useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handleClick = (n) => {
    if (!n.read) markRead.mutate(n.id);
    setOpen(false);
    // A notification with a link points at a job; route to the Inbox so the
    // operator can see the request + its report.
    if (n.link && onNav) onNav("inbox", n.link);
  };

  return (
    <div className="notif-wrap" ref={wrapRef}>
      <button
        className="btn btn-icon btn-ghost"
        title="Notifications"
        aria-label="Notifications"
        aria-expanded={open}
        style={{ position: "relative" }}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="bell" s={14} />
        {unread > 0 ? (
          <span className="notif-badge">{unread > 99 ? "99+" : unread}</span>
        ) : (
          <span className="notif-dot" style={{ position: "absolute", top: 5, right: 5, opacity: 0.3 }} />
        )}
      </button>

      {open && (
        <div className="notif-panel" role="menu">
          <div className="notif-panel-head">
            <span style={{ fontWeight: 600, fontSize: "var(--t-13)" }}>
              Notifications
            </span>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ height: 24, fontSize: 11 }}
              disabled={unread === 0 || markAll.isPending}
              onClick={() => markAll.mutate()}
            >
              Mark all read
            </button>
          </div>
          <div className="notif-panel-list">
            {items.length === 0 && (
              <div className="muted" style={{ padding: 18, textAlign: "center", fontSize: "var(--t-13)" }}>
                You're all caught up.
              </div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                type="button"
                className={`notif-row${n.read ? "" : " is-unread"}`}
                onClick={() => handleClick(n)}
              >
                <span className={`pill pill-${KIND_TONE[n.kind] || "neutral"}`} style={{ flexShrink: 0 }}>
                  <span className="pill-dot" />
                </span>
                <span className="col" style={{ minWidth: 0, flex: 1, textAlign: "left" }}>
                  <span className="truncate" style={{ fontSize: "var(--t-13)", fontWeight: n.read ? 400 : 600 }}>
                    {n.title}
                  </span>
                  {n.body && (
                    <span className="muted truncate" style={{ fontSize: 11 }}>
                      {n.body}
                    </span>
                  )}
                  <span className="faint" style={{ fontSize: 10.5 }}>
                    {n.source} · {relativeTime(n.created_at)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
