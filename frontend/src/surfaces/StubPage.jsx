import { Icon } from "../components/atoms.jsx";

export const StubPage = ({ title, subtitle }) => (
  <div className="page-fade" style={{ padding: "16px 20px" }}>
    <h1 style={{ margin: 0, fontSize: "var(--t-24)", fontWeight: 600 }}>{title}</h1>
    <p className="muted" style={{ margin: "2px 0 18px", fontSize: "var(--t-13)" }}>{subtitle}</p>
    <div
      className="card"
      style={{ padding: 60, textAlign: "center", color: "var(--fg-muted)" }}
    >
      <Icon name="dashboard" s={28} style={{ color: "var(--fg-faint)", marginBottom: 12 }} />
      <div style={{ fontSize: "var(--t-14)" }}>This surface is sketched in the IA — designed in sprint 5–6.</div>
    </div>
  </div>
);
