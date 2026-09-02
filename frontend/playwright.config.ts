import { defineConfig, devices } from '@playwright/test'

// Points at the existing Vite dev server (:5190) by default — the same instance used for
// manual verification all along, not a separate CI-only build. Override PLAYWRIGHT_BASE_URL
// to point at a different environment (e.g. a CI-provisioned one).
//
// fullyParallel/workers deliberately conservative when running against that shared,
// real instance (55 real Agents + real técnicos may be using it): a burst of concurrent
// page loads once genuinely exhausted the backend's DB connection pool and took the
// whole thing down (see app/core/database.py's pool_size comment). CI, hitting its own
// disposable backend+DB, can safely override both back to full parallelism.
const isSharedLiveInstance = !process.env.PLAYWRIGHT_BASE_URL

export default defineConfig({
  testDir: './e2e',
  fullyParallel: !isSharedLiveInstance,
  workers: isSharedLiveInstance ? 1 : undefined,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  // Default 5s expect() timeout is tight for the shared live instance — 55 real Agents
  // constantly hitting the DB (heartbeats, metric history) add real tail latency to
  // login/page-load that a disposable CI backend under no such load wouldn't have.
  expect: { timeout: isSharedLiveInstance ? 15_000 : 5_000 },
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://172.20.1.51:5190',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
