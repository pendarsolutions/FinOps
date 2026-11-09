import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Pendar's design system as scripts/pull-pendar.sh generates it into the app (tokens, font, icons, logo), so the site
// and the app always match. If the site moves to its own repository, copy that folder and point this alias at it.
const pendar = fileURLToPath(new URL("../apps/web/src/pendar", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@pendar": pendar } },
  server: { port: 5174, fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] } },
});
