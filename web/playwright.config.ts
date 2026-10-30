import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8100;
const WEB_PORT = 4173;
const databaseUrl =
  process.env.E2E_DATABASE_URL ?? "postgresql+psycopg://postgres@127.0.0.1:5432/reel2play_e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "phone", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: `uv run alembic upgrade head && uv run uvicorn reel2play.main:app --port ${API_PORT}`,
      cwd: "../api",
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: databaseUrl,
        APP_ENV: "local",
        AI_MODE: "mock",
        STORAGE_BACKEND: "local",
        LOCAL_MEDIA_DIR: "var/e2e-media",
        WORKER_ENABLED: "true",
        WORKER_POLL_SECONDS: "0.2",
        API_BASE_URL: `http://127.0.0.1:${API_PORT}`,
        CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}`,
      },
    },
    {
      command: `npm run build && npx vite preview --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
