import { defineConfig, devices } from "@playwright/test";

// End-to-end tests live in ./e2e (none yet). Start the dev server automatically.
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:8080" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "npm run dev", url: "http://localhost:8080", reuseExistingServer: true },
});
