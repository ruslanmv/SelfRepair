import React from "react";

import { Icon } from "../../components/atoms.jsx";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/StateScreens.jsx";
import {
  useAdminUsers,
  useDeleteUser,
  useSendReset,
  useUpdateUser,
} from "../../hooks/useAdmin.js";

const PAGE_SIZE = 25;

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function RoleBadge({ role, isRoot }) {
  if (isRoot) {
    return (
      <span
        className="chip"
        title="Protected superuser — created on first run"
        style={{ borderColor: "var(--brand)", color: "var(--brand)", fontWeight: 600 }}
      >
        Root
      </span>
    );
  }
  const admin = role === "admin";
  return (
    <span className={`chip ${admin ? "" : "muted"}`}>
      {admin ? "Admin" : "User"}
    </span>
  );
}

function StatusBadges({ user }) {
  return (
    <span className="row gap-2" style={{ flexWrap: "wrap" }}>
      <span className={`pill pill-${user.is_active ? "ok" : "danger"}`}>
        <span className="pill-dot" />
        {user.is_active ? "Active" : "Inactive"}
      </span>
      <span className={`pill pill-${user.email_verified ? "info" : "neutral"}`}>
        {user.email_verified ? "Verified" : "Unverified"}
      </span>
    </span>
  );
}

function ActionsMenu({ user, onAction, busy }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const isAdmin = user.role === "admin";
  // The root superuser is protected: no role/active/delete actions, only a
  // password reset. (The backend also enforces this.)
  const items = user.is_root
    ? [{ key: "send-reset", label: "Send password reset" }]
    : [
        isAdmin
          ? { key: "make-user", label: "Make user", danger: true }
          : { key: "make-admin", label: "Make admin", danger: true },
        user.is_active
          ? { key: "deactivate", label: "Deactivate", danger: true }
          : { key: "activate", label: "Activate" },
        !user.email_verified && { key: "verify", label: "Mark verified" },
        { key: "send-reset", label: "Send password reset" },
        { key: "delete", label: "Delete", danger: true },
      ].filter(Boolean);

  return (
    <div ref={ref} style={{ position: "relative", textAlign: "right" }}>
      <button
        className="btn btn-ghost"
        disabled={busy}
        onClick={() => setOpen((o) => !o)}
        aria-label="Row actions"
        style={{ padding: "2px 8px" }}
      >
        <Icon name="more" s={16} />
      </button>
      {open && (
        <div
          className="card"
          style={{
            position: "absolute",
            right: 0,
            top: "100%",
            zIndex: 20,
            minWidth: 190,
            padding: 4,
            display: "flex",
            flexDirection: "column",
            gap: 2,
          }}
        >
          {items.map((it) => (
            <button
              key={it.key}
              className={`btn btn-ghost ${it.danger ? "btn-danger" : ""}`}
              style={{ justifyContent: "flex-start", width: "100%" }}
              onClick={() => {
                setOpen(false);
                onAction(it.key);
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AdminUsers() {
  const [search, setSearch] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [rowError, setRowError] = React.useState({ id: null, msg: "" });

  const params = {
    query: query || undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const users = useAdminUsers(params);
  const updateUser = useUpdateUser();
  const sendReset = useSendReset();
  const deleteUser = useDeleteUser();

  const busyId =
    updateUser.isPending || sendReset.isPending || deleteUser.isPending
      ? updateUser.variables?.id ||
        sendReset.variables?.id ||
        deleteUser.variables?.id
      : null;

  const submitSearch = (e) => {
    e.preventDefault();
    setOffset(0);
    setQuery(search.trim());
  };

  const showErr = (id, err) => {
    setRowError({
      id,
      msg: err?.detail || err?.message || "Action failed.",
    });
  };

  const onAction = async (user, key) => {
    setRowError({ id: null, msg: "" });
    try {
      if (key === "make-admin") {
        if (!window.confirm(`Grant admin to ${user.email}?`)) return;
        await updateUser.mutateAsync({ id: user.id, patch: { role: "admin" } });
      } else if (key === "make-user") {
        if (!window.confirm(`Demote ${user.email} to a regular user?`)) return;
        await updateUser.mutateAsync({ id: user.id, patch: { role: "user" } });
      } else if (key === "activate") {
        await updateUser.mutateAsync({
          id: user.id,
          patch: { is_active: true },
        });
      } else if (key === "deactivate") {
        if (!window.confirm(`Deactivate ${user.email}? They will lose access.`))
          return;
        await updateUser.mutateAsync({
          id: user.id,
          patch: { is_active: false },
        });
      } else if (key === "verify") {
        await updateUser.mutateAsync({
          id: user.id,
          patch: { email_verified: true },
        });
      } else if (key === "send-reset") {
        await sendReset.mutateAsync({ id: user.id });
        setRowError({ id: user.id, msg: "Password reset email sent." });
      } else if (key === "delete") {
        if (
          !window.confirm(
            `Permanently delete ${user.email}? This cannot be undone.`,
          )
        )
          return;
        await deleteUser.mutateAsync({ id: user.id });
      }
    } catch (err) {
      showErr(user.id, err);
    }
  };

  const items = users.data?.items || [];
  const count = users.data?.count || 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  return (
    <div className="page-fade" style={{ padding: "16px 20px" }}>
      <div style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>
          Users
        </h1>
        <p
          className="muted"
          style={{ margin: "2px 0 0", fontSize: "var(--t-13)" }}
        >
          Manage every account — roles, access, verification and resets.
        </p>
      </div>

      <form
        onSubmit={submitSearch}
        className="card"
        style={{ padding: 12, marginBottom: 12, display: "flex", gap: 8 }}
      >
        <input
          className="input"
          placeholder="Search email, username or name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" type="submit">
          Search
        </button>
        {query && (
          <button
            className="btn"
            type="button"
            onClick={() => {
              setSearch("");
              setQuery("");
              setOffset(0);
            }}
          >
            Clear
          </button>
        )}
      </form>

      <div className="card" style={{ padding: 0, overflow: "visible" }}>
        {users.isLoading && !users.data && <LoadingState label="Loading users…" />}
        {users.isError && (
          <ErrorState
            title="Could not load users"
            message={users.error?.detail || "Please retry."}
            onRetry={() => users.refetch()}
          />
        )}
        {!users.isLoading && !users.isError && items.length === 0 && (
          <EmptyState
            title="No users found"
            message={query ? "No accounts match your search." : "No accounts yet."}
          />
        )}
        {items.length > 0 && (
          <div className="scroll-x-mobile" style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>User</th>
                  <th style={{ width: 90 }}>Role</th>
                  <th style={{ width: 200 }}>Status</th>
                  <th style={{ width: 180 }}>Created</th>
                  <th style={{ width: 180 }}>Last login</th>
                  <th style={{ width: 60 }} />
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <React.Fragment key={u.id}>
                    <tr>
                      <td>
                        <div className="col" style={{ gap: 2 }}>
                          <span style={{ fontWeight: 600 }}>{u.email}</span>
                          <span className="faint mono" style={{ fontSize: 12 }}>
                            @{u.username}
                          </span>
                        </div>
                      </td>
                      <td>
                        <RoleBadge role={u.role} isRoot={u.is_root} />
                      </td>
                      <td>
                        <StatusBadges user={u} />
                      </td>
                      <td className="muted">{fmtDate(u.created_at)}</td>
                      <td className="muted">{fmtDate(u.last_login)}</td>
                      <td>
                        <ActionsMenu
                          user={u}
                          busy={busyId === u.id}
                          onAction={(key) => onAction(u, key)}
                        />
                      </td>
                    </tr>
                    {rowError.id === u.id && rowError.msg && (
                      <tr>
                        <td colSpan={6} style={{ paddingTop: 0 }}>
                          <span
                            className="muted"
                            style={{ fontSize: 12, color: "var(--danger)" }}
                          >
                            {rowError.msg}
                          </span>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div
        className="row"
        style={{ justifyContent: "space-between", marginTop: 12 }}
      >
        <span className="muted" style={{ fontSize: 12 }}>
          {count} user{count === 1 ? "" : "s"} · page {page} of {pages}
        </span>
        <div className="row gap-2">
          <button
            className="btn"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            className="btn"
            disabled={offset + PAGE_SIZE >= count}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
