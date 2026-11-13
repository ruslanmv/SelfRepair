import React from "react";

import { ConnectorHub } from "../features/ConnectorHub.jsx";

// The dedicated Connections navigation entry and Fleet > Settings now share
// the same provider catalogue, setup wizard, and backend connection records.
export function Connections() {
  return (
    <div className="page-fade settings-page">
      <header className="settings-title">
        <h1>Connections</h1>
        <p className="muted">Manage service endpoints and securely pair your AI tools.</p>
      </header>
      <ConnectorHub />
    </div>
  );
}
