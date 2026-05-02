// Atoms: Icon, RepoIcon, Pill, SeverityDot, StateBadge, Avatar, Sparkline, HealthBar.
// Stable visual contract for surfaces; ported from the prototype's atoms2.jsx.

const ICONS = {
  dashboard: "M3 12h7V3H3v9zm0 9h7v-7H3v7zm9 0h9v-9h-9v9zm0-18v7h9V3h-9z",
  repos: "M3 4.5a2.5 2.5 0 0 1 2.5-2.5h13A1.5 1.5 0 0 1 20 3.5v15a1.5 1.5 0 0 1-1.5 1.5h-13A2.5 2.5 0 0 1 3 17.5v-13zM5.5 4a.5.5 0 0 0-.5.5V13h13.5V4h-13zM5 17.5a.5.5 0 0 0 .5.5H18v-3H5v2.5z",
  findings: "M12 2L2 7v6c0 5 4 9 10 9s10-4 10-9V7l-10-5zm0 6a4 4 0 0 1 4 4h-2a2 2 0 1 0-4 0H8a4 4 0 0 1 4-4z",
  repairs: "M14 4l-2 2-7-7-3 3 7 7-2 2 5 5 4-4 4 4 3-3-4-4 4-4-5-5z M5 5l1 1",
  jobs: "M12 2v4 M12 18v4 M4.93 4.93l2.83 2.83 M16.24 16.24l2.83 2.83 M2 12h4 M18 12h4 M4.93 19.07l2.83-2.83 M16.24 7.76l2.83-2.83",
  policies: "M12 2L4 5v7c0 5 3.5 9 8 10 4.5-1 8-5 8-10V5l-8-3z",
  audit: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM8 13h8 M8 17h8 M8 9h4",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z",
  search: "M21 21l-5.2-5.2 M16 10.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z",
  bell: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0",
  caret: "M9 6l6 6-6 6",
  caretDown: "M6 9l6 6 6-6",
  plus: "M12 5v14 M5 12h14",
  retry: "M21 12a9 9 0 1 1-3-6.7L21 8 M21 3v5h-5",
  filter: "M3 6h18 M7 12h10 M11 18h2",
  more: "M12 6h.01 M12 12h.01 M12 18h.01",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6 M15 3h6v6 M10 14L21 3",
  play: "M5 3l14 9-14 9V3z",
  pause: "M6 4h4v16H6zM14 4h4v16h-4z",
  check: "M20 6L9 17l-5-5",
  branch: "M6 3v12 M18 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M15 6a9 9 0 0 0-9 9",
  shield: "M12 2L4 5v7c0 5 3.5 9 8 10 4.5-1 8-5 8-10V5l-8-3z",
  spark: "M12 2L9 9l-7 1 5 5-1 7 6-3 6 3-1-7 5-5-7-1z",
  github: "M9 19c-5 1.5-5-2.5-7-3 M15 22v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 19 5.77 5.07 5.07 0 0 0 18.91 2S17.73 1.65 15 3.5a13.38 13.38 0 0 0-7 0C5.27 1.65 4.09 2 4.09 2A5.07 5.07 0 0 0 4 5.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 8 19.13V22",
  dot: "M12 12.01",
};

export const Icon = ({ name, s = 16, style }) => {
  const path = ICONS[name] || ICONS.dot;
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
    >
      {path.split(" M").map((p, i) => (
        <path key={i} d={(i === 0 ? "" : "M") + p} />
      ))}
    </svg>
  );
};

export const RepoIcon = ({ platform, s = 14 }) => {
  if (platform === "github") return <Icon name="github" s={s} style={{ color: "#9DA5B4" }} />;
  if (platform === "gitlab")
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="#FC6D26">
        <path d="M12 21l-3.5-10.7H15.5L12 21z" opacity="0.9" />
        <path d="M12 21l-7-10.7H8.5L12 21z" opacity="0.7" />
        <path d="M12 21l7-10.7h-3.5L12 21z" opacity="0.7" />
        <path d="M5 10.3L3.8 6.2c-.1-.3.1-.5.4-.6L8.5 5l.5-.1L12 21 5 10.3z" opacity="0.5" />
        <path d="M19 10.3L20.2 6.2c.1-.3-.1-.5-.4-.6L15.5 5l-.5-.1L12 21l7-10.7z" opacity="0.5" />
      </svg>
    );
  if (platform === "huggingface") return <span style={{ fontSize: s, lineHeight: 1 }}>🤗</span>;
  return <Icon name="repos" s={s} />;
};

export const Pill = ({ tone = "neutral", dot, children }) => (
  <span className={`pill pill-${tone}`}>
    {dot && <span className="pill-dot" />}
    {children}
  </span>
);

export const SeverityDot = ({ level }) => {
  const map = {
    critical: { color: "var(--danger)", label: "C" },
    high: { color: "var(--danger)", label: "H" },
    medium: { color: "var(--warn)", label: "M" },
    low: { color: "var(--info)", label: "L" },
    info: { color: "var(--fg-faint)", label: "I" },
  };
  const m = map[level] || map.info;
  return (
    <span
      style={{
        display: "inline-grid",
        placeItems: "center",
        width: 18,
        height: 18,
        borderRadius: 4,
        background: `color-mix(in srgb, ${m.color} 15%, transparent)`,
        color: m.color,
        fontSize: 10,
        fontFamily: "var(--font-mono)",
        fontWeight: 700,
        border: `1px solid color-mix(in srgb, ${m.color} 35%, transparent)`,
      }}
    >
      {m.label}
    </span>
  );
};

export const StateBadge = ({ state }) => {
  const map = {
    "awaiting-approval": { tone: "warn", label: "Awaiting approval" },
    "in-sandbox": { tone: "info", label: "In sandbox" },
    merged: { tone: "ok", label: "Merged" },
    blocked: { tone: "danger", label: "Blocked" },
    "blocked-policy": { tone: "danger", label: "Blocked by policy" },
    running: { tone: "info", label: "Running" },
    succeeded: { tone: "ok", label: "Succeeded" },
    queued: { tone: "neutral", label: "Queued" },
    failed: { tone: "danger", label: "Failed" },
    open: { tone: "warn", label: "Open" },
    suppressed: { tone: "neutral", label: "Suppressed" },
    fixed: { tone: "ok", label: "Fixed" },
    triaging: { tone: "info", label: "Triaging" },
    "in-repair": { tone: "info", label: "In repair" },
  };
  const m = map[state] || { tone: "neutral", label: state };
  return (
    <Pill tone={m.tone} dot>
      {m.label}
    </Pill>
  );
};

export const Avatar = ({ initials, hue = 200 }) => (
  <span
    style={{
      width: 26,
      height: 26,
      borderRadius: 999,
      background: `linear-gradient(135deg, hsl(${hue} 60% 55%), hsl(${hue + 40} 60% 45%))`,
      color: "white",
      fontSize: 10,
      fontWeight: 600,
      display: "grid",
      placeItems: "center",
      flexShrink: 0,
      boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
    }}
  >
    {initials}
  </span>
);

export const Sparkline = ({ data, w = 80, h = 24, stroke = "currentColor", fill }) => {
  if (!data || !data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const points = data.map((v, i) => `${i * step},${h - ((v - min) / range) * (h - 4) - 2}`);
  const path = "M " + points.join(" L ");
  const fillPath = path + ` L ${w},${h} L 0,${h} Z`;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {fill && <path d={fillPath} fill="currentColor" opacity="0.12" />}
      <path
        d={path}
        stroke={stroke}
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

export const HealthBar = ({ value }) => {
  const color =
    value >= 85 ? "var(--ok)" : value >= 65 ? "var(--warn)" : "var(--danger)";
  return (
    <div className="healthbar">
      <div className="healthbar-track">
        <div className="healthbar-fill" style={{ width: `${value}%`, background: color }} />
      </div>
      <span
        className="mono"
        style={{ fontSize: 11, color, minWidth: 22, textAlign: "right" }}
      >
        {value}
      </span>
    </div>
  );
};
