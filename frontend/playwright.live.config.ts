import { defineConfig } from '@playwright/test'
import process from 'node:process'

const apiPort = process.env.SERVICEOS_LIVE_API_PORT || '8000'
const vitePort = process.env.SERVICEOS_LIVE_VITE_PORT || '5173'
const liveBaseUrl = process.env.SERVICEOS_LIVE_BASE_URL || `http://127.0.0.1:${vitePort}`

export default defineConfig({
  testDir: './tests-live',
  outputDir: './test-results/live',
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  use: { baseURL: liveBaseUrl, channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 1000 }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: process.env.SERVICEOS_LIVE_EXTERNAL === '1' ? undefined : [
    { command: `uv run --project ../backend --locked uvicorn serviceos_api.main:app --host 127.0.0.1 --port ${apiPort}`, url: `http://127.0.0.1:${apiPort}/api/v1/health`, reuseExistingServer: false },
    { command: `npm run dev -- --port ${vitePort}`, url: liveBaseUrl, reuseExistingServer: false,
      env: { ...process.env, SERVICEOS_VITE_PORT: vitePort, SERVICEOS_VITE_API_TARGET: `http://127.0.0.1:${apiPort}` } },
  ],
})
