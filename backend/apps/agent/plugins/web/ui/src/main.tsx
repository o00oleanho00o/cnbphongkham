import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app";
import { installSdk } from "./sdk";
import "./styles.css";

installSdk();

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
