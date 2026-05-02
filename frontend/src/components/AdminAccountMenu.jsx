import React from "react";

import { Avatar, Icon } from "./atoms.jsx";

// Account popover modelled on the ChatGPT/Claude profile menu. Single-user
// app — there's only the admin — so the trigger is a full-width sidebar
// footer button (avatar + name + email + caret), and the popover opens
// upward above it.
//
// Props:
//   user        : { name, email, initials, hue }
//   onAction    : (id) => void  — id ∈ {'about','settings','help','logout'}
//
// Behaviour:
//   - Click outside the popover closes it.
//   - Escape closes it.
//   - Selecting an item closes the menu and fires `onAction(id)`.

const ITEMS = [
  { id: "about", label: "About", icon: "dot" },
  { id: "settings", label: "Settings", icon: "settings" },
  { id: "help", label: "Help", icon: "shield" },
  // divider before logout
  { id: "logout", label: "Log out", icon: "external", danger: true },
];

export const AdminAccountMenu = ({ user, onAction }) => {
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef(null);

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

  const pick = (id) => {
    setOpen(false);
    onAction?.(id);
  };

  return (
    <div className="account-wrap" ref={wrapRef}>
      {open && (
        <div className="account-menu" role="menu">
          <div className="account-menu-head">
            <Avatar initials={user.initials} hue={user.hue} />
            <div className="col" style={{ minWidth: 0 }}>
              <span
                className="truncate"
                style={{ fontSize: "var(--t-13)", fontWeight: 500 }}
              >
                {user.name}
              </span>
              <span className="faint truncate" style={{ fontSize: 11 }}>
                {user.email}
              </span>
            </div>
          </div>
          <div className="account-menu-divider" />
          {ITEMS.map((it) => (
            <React.Fragment key={it.id}>
              {it.id === "logout" && <div className="account-menu-divider" />}
              <button
                type="button"
                className={`account-menu-item ${it.danger ? "is-danger" : ""}`}
                role="menuitem"
                onClick={() => pick(it.id)}
              >
                <span className="account-menu-ico">
                  <Icon name={it.icon} s={14} />
                </span>
                <span>{it.label}</span>
              </button>
            </React.Fragment>
          ))}
        </div>
      )}
      <button
        type="button"
        className={`account-trigger ${open ? "is-open" : ""}`}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)}
      >
        <Avatar initials={user.initials} hue={user.hue} />
        <div className="col grow" style={{ minWidth: 0, textAlign: "left" }}>
          <span
            className="truncate"
            style={{ fontSize: "var(--t-13)", fontWeight: 500 }}
          >
            {user.name}
          </span>
          <span className="faint truncate" style={{ fontSize: 11 }}>
            {user.email}
          </span>
        </div>
        <Icon name="caretDown" s={12} style={{ color: "var(--fg-faint)" }} />
      </button>
    </div>
  );
};
