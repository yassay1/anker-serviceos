import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests-live',
  outputDir: './test-results/live',
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  use: { baseURL: 'http://127.0.0.1:5173', channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 1000 }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    { command: 'uv run --project ../backend --locked uvicorn serviceos_api.main:app --host 127.0.0.1 --port 8000', url: 'http://127.0.0.1:8000/api/v1/health', reuseExistingServer: false },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: false },
  ],
})
