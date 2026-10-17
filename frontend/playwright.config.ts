import { defineConfig } from '@playwright/test'

const testPort = process.env.PLAYWRIGHT_PORT || '5175'
const testBaseUrl = `http://127.0.0.1:${testPort}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  workers: 2,
  use: {
    baseURL: testBaseUrl,
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `npm run dev -- --port ${testPort} --strictPort`,
    url: testBaseUrl,
    reuseExistingServer: false,
  },
})
