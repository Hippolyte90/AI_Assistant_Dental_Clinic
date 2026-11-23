import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SessionPage } from "./pages/SessionPage";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SessionPage />
  </StrictMode>,
);
