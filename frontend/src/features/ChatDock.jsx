import React from "react";

import { Icon } from "../components/atoms.jsx";

const SUGGESTED_PROMPTS = {
  findings: ["Why is F-9001 high severity?", "Group similar findings across the fleet", "Which can be auto-fixed safely?"],
  repairs: ["Explain the diff in PR-2210", "Why did policy ALLOW this repair?", "What's the rollback plan?"],
  jobs: ["Why did stage 'heal' take 25s?", "Show comparable past jobs", "Was anything skipped?"],
  default: ["Summarize my fleet status", "What needs my approval today?", "Top recurring fingerprints"],
};

const SAMPLE_REPLY = {
  "Why is F-9001 high severity?":
    "**F-9001** (`missing-pyproject:tool.uv`) is high because it blocks reproducible installs across your fleet. Specifically:\n\n• 14 repos depend on `uv sync` in CI — without `[tool.uv]` they fall back to pip's resolver, producing non-deterministic dep graphs.\n• It cascades: 3 of those repos already opened transient build failures in the last 7 days.\n• The auto-fix template has 0.94 confidence and clears the same finding fleet-wide.\n\nPolicy `allow.auto_fix.pyproject` matches — you can safely batch-repair from the Findings view.",
  "Explain the diff in PR-2210":
    "PR-2210 makes two surgical changes:\n\n1. **Bumps `requires-python`** from `>=3.10` to `>=3.11` to align with the matrixlab-py311 sandbox image (your validation environment).\n2. **Adds `[tool.uv]` block** with pinned dev deps (pytest, ruff, mypy) — this is what lets `uv sync` run hermetically.\n\nIt also generates `tests/test_health.py` so the standard health probe contract is satisfied. All three changes are template-driven (no LLM), reproducible, and signed via cosign.",
};

// Inline markdown-lite renderer (bold + code).
const renderInline = (text) => {
  const parts = [];
  let rest = text;
  let idx = 0;
  while (rest.length) {
    const b = rest.match(/^\*\*(.+?)\*\*/);
    const c = rest.match(/^`(.+?)`/);
    if (b) {
      parts.push(<b key={idx++}>{b[1]}</b>);
      rest = rest.slice(b[0].length);
    } else if (c) {
      parts.push(
        <code
          key={idx++}
          className="mono"
          style={{
            background: "var(--bg-elev-2)",
            padding: "1px 5px",
            borderRadius: 3,
            fontSize: "0.92em",
          }}
        >
          {c[1]}
        </code>,
      );
      rest = rest.slice(c[0].length);
    } else {
      const next = rest.search(/(\*\*|`)/);
      if (next === -1) {
        parts.push(<span key={idx++}>{rest}</span>);
        rest = "";
      } else {
        parts.push(<span key={idx++}>{rest.slice(0, next)}</span>);
        rest = rest.slice(next);
      }
    }
  }
  return parts;
};

export const ChatDock = ({ open, onClose, scope = "default", scopeLabel = "Fleet" }) => {
  const [messages, setMessages] = React.useState([
    {
      role: "assistant",
      text: "Hi — I'm reading your fleet's findings, repairs, jobs, and policy traces. Ask me anything about why things happened, what's safe to auto-repair, or who approved what.",
    },
  ]);
  const [input, setInput] = React.useState("");
  const [thinking, setThinking] = React.useState(false);
  const [cited, setCited] = React.useState(true);
  const endRef = React.useRef(null);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, thinking]);

  const send = (text) => {
    const q = (text || input).trim();
    if (!q) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setThinking(true);
    setTimeout(() => {
      const reply =
        SAMPLE_REPLY[q] ||
        `Looking at your **${scopeLabel}** context, here's what I see:\n\n• I correlated your question against 12 recent audit entries and 3 policy decisions.\n• The relevant signals are scoped to ${scopeLabel.toLowerCase()} only — I'm not pulling beyond it.\n• If you want, I can draft a follow-up action or open a triage ticket.`;
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: reply,
          cites: cited ? ["audit:A-44912", "policy:v3#auto_fix.pyproject", "job:J-77821"] : [],
        },
      ]);
      setThinking(false);
    }, 900);
  };

  const prompts = SUGGESTED_PROMPTS[scope] || SUGGESTED_PROMPTS.default;

  if (!open) return null;
  return (
    <div className="chat-dock">
      <div className="chat-head">
        <div className="row gap-2">
          <span className="brandmark" style={{ width: 22, height: 22, borderRadius: 5 }}>
            <span className="check" style={{ width: 12, height: 12 }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="#0A0E27" strokeWidth="3" strokeLinecap="round">
                <path d="M5 12.5l4.5 4.5L19 7" />
              </svg>
            </span>
          </span>
          <div className="col">
            <span style={{ fontSize: "var(--t-13)", fontWeight: 600 }}>SelfRepair Copilot</span>
            <span className="faint mono" style={{ fontSize: 10.5 }}>scope: {scopeLabel} · OllaBridge · qwen2.5</span>
          </div>
        </div>
        <div className="row gap-2">
          <label className="row gap-2" style={{ fontSize: 11, color: "var(--fg-muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={cited} onChange={(e) => setCited(e.target.checked)} /> Show citations
          </label>
          <button
            className="btn btn-sm btn-ghost btn-icon"
            onClick={onClose}
            title="Hide chat (top-right toggle to reopen)"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="chat-body">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            {m.role === "assistant" && (
              <span className="chat-avatar"><Icon name="spark" s={12} /></span>
            )}
            <div className="col grow">
              <div className="chat-bubble">
                {m.text.split("\n").map((line, j) => {
                  if (line.startsWith("• "))
                    return (
                      <div key={j} style={{ paddingLeft: 16, position: "relative" }}>
                        <span style={{ position: "absolute", left: 4, color: "var(--brand)" }}>•</span>
                        {renderInline(line.slice(2))}
                      </div>
                    );
                  if (line.match(/^\d+\. /))
                    return (
                      <div key={j} style={{ paddingLeft: 18, position: "relative" }}>
                        <span style={{ position: "absolute", left: 0, color: "var(--brand)", fontWeight: 600 }}>
                          {line.match(/^\d+/)[0]}.
                        </span>
                        {renderInline(line.replace(/^\d+\. /, ""))}
                      </div>
                    );
                  if (!line.trim()) return <div key={j} style={{ height: 6 }} />;
                  return <div key={j}>{renderInline(line)}</div>;
                })}
              </div>
              {m.cites && m.cites.length > 0 && (
                <div className="row gap-2" style={{ marginTop: 5, flexWrap: "wrap" }}>
                  {m.cites.map((c, j) => (
                    <span key={j} className="cite mono">{c}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {thinking && (
          <div className="chat-msg chat-assistant">
            <span className="chat-avatar"><Icon name="spark" s={12} /></span>
            <div className="chat-bubble">
              <span className="dots"><span /><span /><span /></span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chat-prompts">
        {prompts.map((p, i) => (
          <span key={i} className="chip" onClick={() => send(p)}>{p}</span>
        ))}
      </div>

      <div className="chat-input-row">
        <input
          className="input grow"
          placeholder={`Ask about ${scopeLabel.toLowerCase()}…`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
        />
        <button className="btn btn-primary" onClick={() => send()}>
          <Icon name="play" s={11} /> Send
        </button>
      </div>
    </div>
  );
};

export const ChatToggle = ({ active, onClick }) => (
  <button
    className={`chat-toggle ${active ? "is-on" : ""}`}
    onClick={onClick}
    title={active ? "Hide AI chat" : "Show AI chat"}
  >
    <span className="chat-toggle-ico"><Icon name="spark" s={13} /></span>
    <span style={{ fontSize: "var(--t-12)", fontWeight: 500 }}>
      {active ? "Hide AI" : "Ask AI"}
    </span>
    {!active && <span className="chat-toggle-dot" />}
  </button>
);
