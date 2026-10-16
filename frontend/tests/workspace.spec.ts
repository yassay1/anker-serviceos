import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { fixture, ids } from './workspace-fixture'

async function quietStream(page: Page) {
  await page.addInitScript(() => {
    class QuietEventSource {
      onopen: (() => void) | null = null
      onerror: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      closed = false
      constructor() { setTimeout(() => { if (!this.closed) this.onopen?.() }, 0) }
      close() { this.closed = true }
    }
    window.EventSource = QuietEventSource as unknown as typeof EventSource
  })
}

test('adaptation: search and status filter operate on loaded conversations', async ({ page }) => {
  const state = await fixture(page)
  await page.goto('/desk')
  const list = page.getByRole('complementary', { name: '会话列表', exact: true })
  await page.getByLabel('搜索已加载的会话').fill('22222222')
  await expect(list.getByRole('button', { name: /22222222/ })).toBeVisible()
  await expect(list.getByRole('button', { name: /11111111/ })).toHaveCount(0)
  await page.getByLabel('搜索已加载的会话').clear()
  await list.getByRole('button', { name: '进行中', exact: true }).click()
  await expect(list.getByRole('button', { name: /22222222/ })).toHaveCount(0)
  await expect(list.getByRole('button', { name: /11111111/ })).toBeVisible()
  expect(state.unexpected).toEqual([])
})

test('adaptation: drafts and visibility stay with their conversation', async ({ page }) => {
  const state = await fixture(page)
  state.conversations[1].status = 'ACTIVE'
  await page.goto('/desk')
  await page.getByLabel('回复客户').fill('会话 A 的内部记录')
  await page.getByRole('button', { name: '内部备注', exact: true }).click()
  const list = page.getByRole('complementary', { name: '会话列表', exact: true })
  await list.getByRole('button', { name: /22222222/ }).click()
  await expect(page.getByLabel('回复客户')).toHaveValue('')
  await expect(page.getByRole('button', { name: '内部备注', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await page.getByLabel('回复客户').fill('会话 B 的公开回复')
  await list.getByRole('button', { name: /11111111/ }).click()
  await expect(page.getByLabel('回复客户')).toHaveValue('会话 A 的内部记录')
  await expect(page.getByRole('button', { name: '内部备注', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '保存内部备注', exact: true }).click()
  await expect.poll(() => state.sent.length).toBe(1)
  expect(state.sent[0]).toMatchObject({ visibility: 'INTERNAL', content: [{ type: 'text', text: '会话 A 的内部记录' }] })
})

test('conversation: specialist result has its own author and no Agent quick replies', async ({ page }) => {
  const state = await fixture(page)
  state.messages.push({
    id: '77777777-7777-4777-8777-777777777777', conversation_id: ids.conversation,
    author_kind: 'SPECIALIST', author_display_name: '诊断专家', visibility: 'INTERNAL',
    content: [{ type: 'text', text: '初步假设（待核验）：可能是电源连接不稳定。' }],
    client_message_id: null, related_case_id: null, created_at: state.messages[0].created_at,
  })
  await page.goto('/desk')
  const specialist = page.locator('.message.author-specialist')
  await expect(specialist.getByText('诊断专家', { exact: true })).toBeVisible()
  await expect(specialist.getByText('AI 假设（待核验）', { exact: true })).toBeVisible()
  await expect(specialist.getByText('仅客服可见', { exact: true })).toBeVisible()
  await expect(specialist.getByText('初步假设（待核验）：可能是电源连接不稳定。', { exact: true })).toBeVisible()
  await expect(specialist.getByRole('button')).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})

test('adaptation: narrow screen panels preserve the message draft', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await fixture(page, false)
  await page.goto('/support')
  await page.getByLabel('描述你的问题').fill('充电宝无法持续充电')
  await page.getByRole('button', { name: '资料与协助', exact: true }).click()
  await expect(page.getByRole('button', { name: '请求真人协助', exact: true })).toBeVisible()
  await expect(page.getByLabel('描述你的问题')).toBeHidden()
  await page.getByRole('button', { name: '请求真人协助', exact: true }).click()
  await expect(page.getByRole('button', { name: '提交协助请求', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '提交协助请求', exact: true })).toHaveCount(1)
  await expect(page.getByLabel('描述你的问题')).toHaveValue('充电宝无法持续充电')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }]) {
  test(`customer conversation: ${viewport.width}px layout has one assistance entry and no runtime completion card`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const state = await fixture(page, false)
    await page.goto('/support')
    await expect(page.locator('.conversation-selector .conversation-list')).toBeVisible()
    await expect(page.getByRole('heading', { name: '对话', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '开始新对话', exact: true })).toHaveCount(1)
    await expect(page.locator('.conversation-list').getByRole('button', { name: '新建会话', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '请求真人协助', exact: true })).toHaveCount(1)
    await expect(page.getByRole('button', { name: '查看协助与补充信息', exact: true })).toHaveCount(0)
    await expect(page.getByText(/交互卡修订|本轮处理结束|本轮运行结束/)).toHaveCount(0)
    expect(state.unexpected).toEqual([])
  })
}

test('adaptation: draft review requires the backend minimum reason length', async ({ page }) => {
  await fixture(page)
  await page.goto('/desk')
  await page.getByRole('button', { name: '人工协作与审批', exact: true }).click()
  await page.getByLabel('原因', { exact: true }).fill('短')
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '拒绝', exact: true })).toBeDisabled()
})

test('adaptation: device details show actual facts and history without verifying identity', async ({ page }) => {
  const identityErrors: string[] = []
  page.on('console', message => { if (message.type() === 'error' && message.text().includes('same key')) identityErrors.push(message.text()) })
  const state = await fixture(page, false)
  await page.goto(`/devices/${ids.device}`)
  await expect(page.getByRole('heading', { name: 'Anker 737', exact: true })).toBeVisible()
  await expect(page.getByText('身份待核验', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('人工测量记录')).toBeVisible()
  await expect(page.getByText('充电接口不稳定', { exact: true })).toBeVisible()
  await expect(page.getByText('PRIVATE-SERIAL-0921', { exact: true })).toHaveCount(0)
  expect(state.unexpected).toEqual([])
  expect(identityErrors).toEqual([])
})

test('adaptation: explicit forbidden device never falls back to another record', async ({ page }) => {
  await fixture(page, false)
  await page.route(`**/api/v1/devices/${ids.second}`, route => route.fulfill({ status: 404, json: { detail: '设备不存在或无权访问。' } }))
  await page.goto(`/devices/${ids.second}`)
  await expect(page.getByRole('alert')).toContainText('设备不存在或无权访问。')
  await expect(page.getByRole('heading', { name: 'Anker 737', exact: true })).toHaveCount(0)
})

test('adaptation: a connected but quiet event stream still reconciles saved messages', async ({ page }) => {
  // Model transport-open without delivered events; HTTP still uses the real Client.
  await quietStream(page)
  const state = await fixture(page, false)
  await page.goto('/support')
  await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
  await expect(page.getByText('充电宝连接后供电不稳定，需要重新插拔才有反应。', { exact: true })).toBeVisible()
  state.messages.push({ ...state.messages[1], id: crypto.randomUUID(), content: [{ type: 'text', text: '这条服务器回复没有触发事件' }] })
  await expect(page.getByText('这条服务器回复没有触发事件', { exact: true })).toBeVisible({ timeout: 12_000 })
  expect(state.unexpected).toEqual([])
})

test('adaptation: a quiet event stream also reconciles externally reviewed drafts', async ({ page }) => {
  await quietStream(page)
  const state = await fixture(page)
  await page.goto('/desk')
  await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '人工协作与审批', exact: true }).click()
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeVisible()
  state.proposals[0].status = 'REJECTED'
  await expect(page.getByText('回复草稿 · 建议补充充电线材信息。 · 已拒绝', { exact: true })).toBeVisible({ timeout: 12_000 })
  await expect(page.getByRole('button', { name: '批准', exact: true })).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})

for (const [route, staff, mobile] of [['/desk', true, false], ['/desk', true, true], ['/support', false, false], ['/support', false, true], [`/devices/${ids.device}`, false, false], [`/devices/${ids.device}`, false, true]] as const) {
  test(`adaptation: accessible ${route} ${mobile ? 'mobile' : 'desktop'} capture`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    const state = await fixture(page, staff)
    await page.goto(route)
    if (route.includes('/devices')) await expect(page.getByText('人工测量记录')).toBeVisible()
    else await expect(page.getByLabel(staff ? '回复客户' : '描述你的问题')).toBeVisible()
    const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    expect(scan.violations).toEqual([])
    expect(state.unexpected).toEqual([])
    await page.screenshot({ path: `test-results/adaptation-${staff ? 'desk' : route.includes('devices') ? 'devices' : 'support'}-${mobile ? 'mobile' : 'desktop'}.png`, fullPage: true })
  })
}
