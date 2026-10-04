import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { OwnerDashboard } from "./OwnerDashboard";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {window.location.pathname.replace(/\/$/,'') === '/owner' ? <OwnerDashboard /> : <App />}
  </StrictMode>,
);
