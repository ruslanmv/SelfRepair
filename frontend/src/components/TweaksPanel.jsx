import React from "react";

import { Icon } from "./atoms.jsx";

// Production trim of the design-tool tweaks panel.
//
// Removed:
//   - parent.postMessage host-integration (design-tool only)
//   - "Try the flows" demo buttons
//   - colour-picker / number-scrubber controls (overkill for end users)
//
// Kept:
//   - theme (dark/light)
//   - accent (violet/cyan/green/orange/blue) — the brand gradient
//   - density (compact/comfortable/spacious)
//   - repos layout (table/cards)
//   - chat reset on navigation toggle
// Preferences are persisted to localStorage so reloads keep settings.

const STORAGE_KEY = "selfrepair.tweaks.v1";

export const TWEAK_DEFAULTS = {
  theme: "dark",
  accent: "violet",
  density: "comfortable",
  reposLayout: "table",
  chatScopedToPage: true,
  showHeroGradient: true,
  showSparklines: true,
};

export const ACCENT_MAP = {
  violet: { brand: "#8B5CF6", brand2: "#06B6D4", grad: "linear-gradient(135deg, #8B5CF6 0%, #06B6D4 100%)" },
  cyan: { brand: "#06B6D4", brand2: "#22D3EE", grad: "linear-gradient(135deg, #0891B2 0%, #22D3EE 100%)" },
  green: { brand: "#10B981", brand2: "#34D399", grad: "linear-gradient(135deg, #059669 0%, #34D399 100%)" },
  orange: { brand: "#F97316", brand2: "#FB923C", grad: "linear-gradient(135deg, #EA580C 0%, #FB923C 100%)" },
  blue: { brand: "#3B82F6", brand2: "#60A5FA", grad: "linear-gradient(135deg, #2563EB 0%, #60A5FA 100%)" },
};

export function useTweaks() {
  const [values, setValues] = React.useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return { ...TWEAK_DEFAULTS, ...JSON.parse(stored) };
    } catch {
      // ignore quota / parse errors
    }
    return TWEAK_DEFAULTS;
  });

  const setTweak = React.useCallback((key, val) => {
    setValues((prev) => {
      const next = { ...prev, [key]: val };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // quota exceeded — in-memory only this session
      }
      return next;
    });
  }, []);

  return [values, setTweak];
}

export function TweaksPanel({ values, setTweak }) {
  const [open, setOpen] = React.useState(false);

  return (
    <>
      <button
        className="tweaks-fab"
        title={open ? "Close tweaks" : "Open tweaks"}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="settings" s={16} />
      </button>
      {open && (
        <div className="tweaks-panel" role="dialog" aria-label="Tweaks">
          <div className="tweaks-head">
            <b>Tweaks</b>
            <button
              className="btn btn-icon btn-ghost btn-sm"
              aria-label="Close tweaks"
              onClick={() => setOpen(false)}
            >
              ✕
            </button>
          </div>
          <div className="tweaks-body">
            <Section label="Theme">
              <Seg
                value={values.theme}
                options={[
                  { value: "dark", label: "Dark" },
                  { value: "light", label: "Light" },
                ]}
                onChange={(v) => setTweak("theme", v)}
              />
            </Section>

            <Section label="Accent">
              <Seg
                value={values.accent}
                options={[
                  { value: "violet", label: "Violet" },
                  { value: "cyan", label: "Cyan" },
                  { value: "green", label: "Green" },
                  { value: "orange", label: "Orange" },
                  { value: "blue", label: "Blue" },
                ]}
                onChange={(v) => setTweak("accent", v)}
              />
            </Section>

            <Section label="Density">
              <Seg
                value={values.density}
                options={[
                  { value: "compact", label: "Compact" },
                  { value: "comfortable", label: "Cozy" },
                  { value: "spacious", label: "Spacious" },
                ]}
                onChange={(v) => setTweak("density", v)}
              />
            </Section>

            <Section label="Repos layout">
              <Seg
                value={values.reposLayout}
                options={[
                  { value: "table", label: "Table" },
                  { value: "cards", label: "Cards" },
                ]}
                onChange={(v) => setTweak("reposLayout", v)}
              />
            </Section>

            <Section label="AI Chat">
              <Toggle
                label="Reset chat per page"
                value={values.chatScopedToPage}
                onChange={(v) => setTweak("chatScopedToPage", v)}
              />
            </Section>

            <Section label="Surfaces">
              <Toggle
                label="Hero gradient"
                value={values.showHeroGradient}
                onChange={(v) => setTweak("showHeroGradient", v)}
              />
              <Toggle
                label="Sparklines on KPIs"
                value={values.showSparklines}
                onChange={(v) => setTweak("showSparklines", v)}
              />
            </Section>
          </div>
        </div>
      )}
    </>
  );
}

function Section({ label, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="tweaks-section-label">{label}</span>
      {children}
    </div>
  );
}

function Seg({ value, options, onChange }) {
  return (
    <div className="tweaks-seg">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={value === o.value ? "is-active" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <div className="tweaks-row" style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
      <span className="tweaks-row-label">{label}</span>
      <button
        type="button"
        className={`tweaks-toggle ${value ? "is-on" : ""}`}
        role="switch"
        aria-checked={!!value}
        onClick={() => onChange(!value)}
      >
        <i />
      </button>
    </div>
  );
}
