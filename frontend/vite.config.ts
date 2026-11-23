import { defineConfig } from "vite";

// Vite is the build tool of the page. "npm run dev" starts its small server, which gives the page to the browser
// and turns the TypeScript files into JavaScript on the way.
export default defineConfig({
  // The page is always served from this address: it is the one that the API names in its CORS setting
  // (PAGE_ORIGINS in backend/config/constants.py). With strictPort, Vite stops instead of picking another port
  server: { port: 5173, strictPort: true },
  // How the JSX of the .tsx files becomes JavaScript: with React's own functions, imported automatically.
  // It is Vite's default. It is written here because no React plugin is installed: the page keeps its packages
  // to React, TypeScript, and Vite
  oxc: { jsx: { runtime: "automatic" } },
});
