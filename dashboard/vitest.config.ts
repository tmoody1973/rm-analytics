import { defineConfig } from "vitest/config";
import path from "path";

// A tiny vite plugin that intercepts CSS imports and returns an empty module.
// Needed because @copilotkit/react-core/v2 does `import "./index.css"` inside
// its MJS bundle, which Node / vitest node-env cannot handle natively.
const cssStub = () => ({
  name: "css-stub",
  resolveId(id: string, importer?: string) {
    if (id.endsWith(".css")) {
      return "\0css-stub";
    }
  },
  load(id: string) {
    if (id === "\0css-stub") {
      return "export default {}";
    }
  },
});

export default defineConfig({
  plugins: [cssStub()],
  test: {
    environment: "node",
    globals: false,
    // Process @copilotkit through Vite so the cssStub plugin above takes
    // effect (node env otherwise bypasses Vite transforms for node_modules).
    server: {
      deps: {
        inline: [/@copilotkit\//, /@clerk\//],
      },
    },
  },
});
