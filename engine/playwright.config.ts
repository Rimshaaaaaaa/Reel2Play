import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  fullyParallel: true,
  reporter: process.env.CI ? "github" : "list",
  projects: [
    { name: "phone-360", use: { ...devices["Desktop Chrome"], viewport: { width: 360, height: 640 }, hasTouch: true } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } } },
  ],
});
