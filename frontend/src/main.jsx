import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";

import "./styles/tokens.css";
import "./styles/ui.css";
import "./styles/features.css";

import App from "./App.jsx";
import { makeQueryClient } from "./api/queryClient.js";

// One QueryClient for the whole SPA. Re-instantiating per render would
// blow the cache on every hot-reload; keep it module-level.
const queryClient = makeQueryClient();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
