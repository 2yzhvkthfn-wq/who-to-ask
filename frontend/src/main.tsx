// The entry point of the page: it puts the App component into the element of index.html.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const root = document.getElementById("root");
if (root) {
  // StrictMode is React's own checker: while the page is developed, it warns about mistakes in the components
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
