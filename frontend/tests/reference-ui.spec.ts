import { expect, test } from '@playwright/test'
import { fixture } from './workspace-fixture'
import AxeBuilder from '@axe-core/playwright'

test('customer home sends the description in the same action that creates a conversation', async ({ page }) => {
  const state = await fixture(page, false)
  state.conversations[1].status = 'ACTIVE'
  const creates: unknown[] = []
  await page.route('**/api/v1/conversations', route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { items: state.conversations } })
    creates.push(route.request().postDataJSON())
    return route.fulfill({ json: state.conversations[1] })
  })
  await page.route('**/api/v1/cases', route => route.fulfill({ json: [] }))
  await page.goto('/')
  await page.getByLabel('问题描述').fill('指示灯没有亮，请帮我检查')
  await page.getByRole('button', { name: '开始新的诊断', exact: true }).click()
  await expect(page).toHaveURL(/\/support\?conversation=/)
  await expect(page.getByText('指示灯没有亮，请帮我检查', { exact: true })).toBeVisible()
  expect(state.sent).toHaveLength(1)
  expect(state.sent[0]).toMatchObject({
    content: [{ type: 'text', text: '指示灯没有亮，请帮我检查' }],
    visibility: 'PUBLIC',
  })
  expect(creates).toEqual([{}])
  await expect(page).toHaveURL(new RegExp(state.conversations[1].id))
})

test('customer home image attachment reuses the conversation case upload flow', async ({ page }) => {
  const state = await fixture(page, false)
  state.conversations[1].status = 'ACTIVE'
  let creates = 0
  await page.route('**/api/v1/conversations', route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { items: state.conversations } })
    creates += 1
    return route.fulfill({ json: state.conversations[1] })
  })
  await page.route('**/api/v1/cases', route => route.fulfill({ json: [] }))
  await page.goto('/')
  await page.getByRole('button', { name: '上传图片' }).click()
  await expect(page.getByRole('dialog', { name: '上传问题图片' })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认创建服务案例并上传图片' })).toBeVisible()
  expect(creates).toBe(1)
  await expect(page).toHaveURL('/')
})

test('customer home voice input transcribes into the description before sending', async ({ page }) => {
  await page.addInitScript(() => {
    class SpeechMock {
      lang = ''
      continuous = false
      interimResults = false
      onresult: ((event: { results: ArrayLike<{ 0?: { transcript: string } }> }) => void) | null = null
      onerror: ((event: { error: string }) => void) | null = null
      onend: (() => void) | null = null
      start() { this.onresult?.({ results: [{ 0: { transcript: '语音录入的问题' } }] }) }
      stop() { this.onend?.() }
      abort() { this.onend?.() }
    }
    Object.defineProperty(window, 'SpeechRecognition', { value: SpeechMock })
  })
  const state = await fixture(page, false)
  state.conversations[1].status = 'ACTIVE'
  await page.route('**/api/v1/conversations', route => route.request().method() === 'GET'
    ? route.fulfill({ json: { items: state.conversations } })
    : route.fulfill({ json: state.conversations[1] }))
  await page.route('**/api/v1/cases', route => route.fulfill({ json: [] }))
  await page.goto('/')
  await page.getByRole('button', { name: '语音输入' }).click()
  await expect(page.getByRole('button', { name: '停止识别' })).toBeVisible()
  await page.getByRole('button', { name: '停止识别' }).click()
  await expect(page.getByLabel('问题描述')).toHaveValue('语音录入的问题')
  await page.getByRole('button', { name: '开始新的诊断', exact: true }).click()
  await expect(page.getByText('语音录入的问题', { exact: true })).toBeVisible()
  expect(state.sent).toHaveLength(1)
  expect(state.sent[0].content).toEqual([{ type: 'text', text: '语音录入的问题' }])
})

test('staff overview filters real case rows and opens the original case route', async ({ page }) => {
  await fixture(page)
  await page.route('**/api/v1/cases', route => route.fulfill({ json: [
    { id: 'case-a', problem_text: '电源无法启动', status: 'WAITING_CUSTOMER', created_at: '2026-10-14T01:00:00Z', customer_id: 'customer-a', version: 1, user_goal: null },
    { id: 'case-b', problem_text: '线材更换完成', status: 'RESOLVED', created_at: '2026-10-14T01:00:00Z', customer_id: 'customer-b', version: 2, user_goal: null },
  ] }))
  await page.goto('/desk?view=overview')
  await expect(page.getByRole('heading', { name: '你好，协作测试客服' })).toBeVisible()
  await page.locator('.staff-filter-tabs').getByRole('button', { name: /^已解决/ }).click()
  await expect(page.getByRole('link', { name: '线材更换完成', exact: true })).toHaveAttribute('href', '/cases/case-b')
  await expect(page.getByRole('link', { name: '电源无法启动', exact: true })).toHaveCount(0)
})

test('customer home keeps the draft after a failed conversation creation', async ({ page }) => {
  const state = await fixture(page, false)
  await page.route('**/api/v1/cases', route => route.fulfill({ json: [] }))
  let creates = 0
  await page.route('**/api/v1/conversations', route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { items: state.conversations } })
    creates += 1
    return route.fulfill({ status: 503, json: { detail: '会话暂时无法建立，请稍后重试。' } })
  })
  await page.goto('/')
  await expect(page.getByRole('button', { name: '开始新的诊断', exact: true })).toBeDisabled()
  expect(creates).toBe(0)
  await page.getByLabel('问题描述').fill('保留这个尚未发送的问题')
  await page.getByRole('button', { name: '开始新的诊断', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('暂时无法建立')
  await expect(page.getByLabel('问题描述')).toHaveValue('保留这个尚未发送的问题')
  await expect(page).toHaveURL('/')
  expect(creates).toBe(1)
  expect(state.sent).toHaveLength(0)
})

test('customer cannot open staff overview or trigger its aggregate queries', async ({ page }) => {
  const state = await fixture(page, false)
  await page.goto('/desk?view=overview')
  await expect(page.getByRole('heading', { name: '此页面仅供客服使用' })).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})

test('overview query failure shows a retry and no invented case total', async ({ page }) => {
  await fixture(page)
  let failed = true
  await page.route('**/api/v1/cases', route => route.fulfill(failed
    ? { status: 503, json: { detail: '案例暂时不可用。' } } : { json: [] }))
  await page.goto('/desk?view=overview')
  const casesPanel = page.locator('.staff-queue')
  await expect(casesPanel.getByRole('alert')).toContainText('案例暂时不可用')
  await expect(page.locator('.staff-summary-card').nth(2).locator('strong')).toHaveText('—')
  failed = false
  await casesPanel.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByRole('heading', { name: '没有符合条件的案例' })).toBeVisible()
  await expect(page.locator('.staff-summary-card').nth(2).locator('strong')).toHaveText('0')
})

for (const mobile of [false, true]) {
  for (const surface of ['home', 'overview', 'case'] as const) {
    test(`reference surfaces: ${surface} ${mobile ? 'mobile' : 'desktop'} keeps accessible content in its viewport`, async ({ page }) => {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1448, height: 1086 })
      const state = await fixture(page, surface === 'overview')
      const serviceCase = { id: '77777777-7777-4777-8777-777777777777', problem_text: '充电连接需要检查', status: 'OPEN', created_at: '2026-10-14T01:00:00Z', customer_id: state.actor.actor_id, version: 1, user_goal: '恢复稳定连接' }
      await page.route('**/api/v1/cases**', route => {
        const path = new URL(route.request().url()).pathname
        return route.fulfill({ json: path === '/api/v1/cases' ? [serviceCase] : path.endsWith(serviceCase.id) ? serviceCase : path.endsWith('/evidence') ? { items: [], next_cursor: null } : [] })
      })
      await page.goto(surface === 'home' ? '/' : surface === 'overview' ? '/desk?view=overview' : `/cases/${serviceCase.id}`)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('充电连接需要检查', { exact: true }).first()).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
      expect(scan.violations).toEqual([])
      expect(state.unexpected).toEqual([])
    })
  }
}
