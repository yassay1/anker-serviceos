import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/api/schema'

type Schemas = components['schemas']
const conversationId = '00000000-0000-4000-8000-000000000001'
const taskId = '00000000-0000-4000-8000-000000000002'
const proposalId = '00000000-0000-4000-8000-000000000003'
const createdAt = '2026-10-14T00:00:00Z'

// Transport fixtures only: these tests neither run nor attest the backend.
async function openDesk(page: Page) {
  const actor: Schemas['ActorRead'] = {
    tenant_id: '00000000-0000-4000-8000-000000000004',
    actor_id: '00000000-0000-4000-8000-000000000005',
    kind: 'STAFF', display_name: '测试客服', role: 'STAFF',
  }
  const state = {
    conversation: {
      id: conversationId, customer_id: '00000000-0000-4000-8000-000000000006',
      status: 'ACTIVE', collaboration_mode: 'AI_LEAD', reply_policy: 'AI_AUTO',
      version: 1, created_at: createdAt,
    } satisfies Schemas['ConversationRead'],
    task: {
      id: taskId, conversation_id: conversationId, case_id: null,
      reason: '请协助检查充电问题', status: 'OPEN', version: 1,
      assignee_id: null as string | null, created_at: createdAt,
    } satisfies Schemas['TaskRead'],
    proposal: {
      id: proposalId, conversation_id: conversationId, created_at: createdAt,
      proposal_type: 'REPLY', payload: { summary: '建议检查线材' }, status: 'DRAFT',
    } satisfies Schemas['ProposalRead'],
    uiReads: 0,
    mutations: [] as { path: string, body: unknown }[],
    unexpected: [] as string[],
  }
  const document: Schemas['UIDocumentRead'] = {
    ui_id: '00000000-0000-4000-8000-000000000007', revision: 1,
    schema_version: 1, catalog_version: 1, audience: 'STAFF', visibility: 'INTERNAL',
    surface: 'DESK_PANEL', status: 'ACTIVE', components: [],
    created_at: createdAt, expires_at: null, source_agent_run_id: null,
    fallback_text: '请继续使用文字消息。',
  }
  const health: Schemas['HealthResponse'] = { status: 'ok', service: 'serviceos-api', version: '0.1.0' }
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (method === 'GET' && path.endsWith('/events')) return route.abort()
    const data = method === 'GET' && path.endsWith('/auth/me') ? actor
      : method === 'GET' && path.endsWith('/health') ? health
      : method === 'GET' && path.endsWith('/conversations') ? { items: [state.conversation] }
      : method === 'GET' && path.endsWith('/messages') ? { items: [], next_cursor: null }
      : method === 'GET' && path.endsWith('/case-summaries') ? []
      : method === 'GET' && path.endsWith('/tasks') ? [state.task]
      : method === 'GET' && path.endsWith('/proposals') ? [state.proposal]
      : method === 'POST' && path.endsWith('/ui-document/refresh') ? document
      : undefined
    if (path.endsWith('/ui-document/refresh')) state.uiReads++
    if (data === undefined) {
      state.unexpected.push(`${method} ${path}`)
      return route.fulfill({ status: 500, json: { detail: 'Unexpected test request' } })
    }
    await route.fulfill({ json: data })
  })
  await page.goto(`/desk?conversation=${conversationId}`)
  const contextButton = page.getByRole('button', { name: '资料', exact: true })
  if (await contextButton.isVisible()) await contextButton.click()
  await expect(page.getByRole('button', { name: '接管', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeVisible()
  return state
}

test('claim conflict refreshes the assigned task without repeating the claim', async ({ page }) => {
  const state = await openDesk(page)
  const uiReads = state.uiReads
  await page.route(`**/tasks/${taskId}/claim`, async (route) => {
    state.mutations.push({ path: 'claim', body: route.request().postDataJSON() })
    state.task.status = 'ASSIGNED'
    state.task.version = 2
    await route.fulfill({ status: 409, json: { detail: '任务已被接管或版本已更新。' } })
  })
  await page.getByRole('button', { name: '接管', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('任务已被接管或版本已更新。')
  await expect(page.getByText('请协助检查充电问题 · 已接管 · 版本 2')).toBeVisible()
  await expect(page.getByRole('button', { name: '接管', exact: true })).toHaveCount(0)
  expect(state.mutations).toEqual([{ path: 'claim', body: { expected_version: 1 } }])
  expect(state.uiReads).toBeGreaterThan(uiReads)
  expect(state.unexpected).toEqual([])
  await page.screenshot({ path: 'test-results/claim-conflict.png', fullPage: true })
})

test('stale mode refreshes the current policy and the next request uses its version', async ({ page }) => {
  const state = await openDesk(page)
  await page.route(`**/conversations/${conversationId}/mode-transitions`, async (route) => {
    state.mutations.push({ path: 'mode', body: route.request().postDataJSON() })
    state.conversation.version = 2
    state.conversation.collaboration_mode = 'HUMAN_LEAD'
    state.conversation.reply_policy = 'HUMAN_ONLY'
    await route.fulfill({ status: 409, json: { detail: '会话版本已更新，请刷新后重试。' } })
  })
  await page.getByLabel('协作模式').selectOption('CO_SERVICE')
  await page.getByRole('button', { name: '切换策略' }).click()
  await expect(page.getByText('当前：真人主导 · 发言策略：仅人工回复 · 版本 2')).toBeVisible()
  await expect(page.getByLabel('协作模式')).toHaveValue('HUMAN_LEAD')
  await expect(page.getByRole('alert')).toHaveText('会话版本已更新，请刷新后重试。')
  expect(state.mutations).toHaveLength(1)
  await page.getByRole('button', { name: '切换策略' }).click()
  await expect.poll(() => state.mutations.length).toBe(2)
  expect(state.mutations[1].body).toMatchObject({ expected_version: 2 })
  expect(state.unexpected).toEqual([])
})

test('version-only conflict resets the draft selection to the unchanged server mode', async ({ page }) => {
  const state = await openDesk(page)
  await page.route(`**/conversations/${conversationId}/mode-transitions`, async (route) => {
    state.mutations.push({ path: 'mode', body: route.request().postDataJSON() })
    state.conversation.version = 2
    await route.fulfill({ status: 409, json: { detail: '会话版本已更新，请刷新后重试。' } })
  })
  await page.getByLabel('协作模式').selectOption('CO_SERVICE')
  await page.getByRole('button', { name: '切换策略' }).click()
  await expect(page.getByText('当前：AI 主导 · 发言策略：授权自动回复 · 版本 2')).toBeVisible()
  await expect(page.getByLabel('协作模式')).toHaveValue('AI_LEAD')
  await expect(page.getByRole('alert')).toHaveText('会话版本已更新，请刷新后重试。')
  expect(state.mutations).toHaveLength(1)
  expect(state.unexpected).toEqual([])
})

test('already decided draft refreshes its rejection at narrow width using the keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const state = await openDesk(page)
  await page.route(`**/proposals/${proposalId}/decision`, async (route) => {
    state.mutations.push({ path: 'decision', body: route.request().postDataJSON() })
    state.proposal.status = 'REJECTED'
    await route.fulfill({ status: 409, json: { detail: '草稿已经决定，不能重复或改变审阅结果。' } })
  })
  await page.getByRole('button', { name: '批准', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('回复草稿 · 建议检查线材 · 已拒绝')).toBeVisible()
  await expect(page.getByRole('button', { name: '批准', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '拒绝', exact: true })).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveText('草稿已经决定，不能重复或改变审阅结果。')
  expect(state.mutations).toHaveLength(1)
  expect(state.mutations[0].body).toMatchObject({ decision: 'APPROVED' })
  expect(state.unexpected).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/draft-conflict-mobile.png', fullPage: true })
})

test('policy conflict keeps a pending draft and shows the server refusal', async ({ page }) => {
  const state = await openDesk(page)
  await page.route(`**/proposals/${proposalId}/decision`, (route) => route.fulfill({
    status: 409, json: { detail: '当前发言策略禁止 Agent 公开回复。' },
  }))
  await page.getByRole('button', { name: '批准', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('当前发言策略禁止 Agent 公开回复。')
  await expect(page.getByText('回复草稿 · 建议检查线材 · 待审阅')).toBeVisible()
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeEnabled()
  expect(state.unexpected).toEqual([])
})

test('forbidden claim never presents an assignment', async ({ page }) => {
  const state = await openDesk(page)
  await page.route(`**/tasks/${taskId}/claim`, (route) => route.fulfill({
    status: 403, json: { detail: '只有客服可接管任务。' },
  }))
  await page.getByRole('button', { name: '接管', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('只有客服可接管任务。')
  await expect(page.getByText('请协助检查充电问题 · 待处理 · 版本 1')).toBeVisible()
  await expect(page.getByRole('button', { name: '接管', exact: true })).toBeEnabled()
  expect(state.unexpected).toEqual([])
})

test('successful claim still refreshes the server assignment', async ({ page }) => {
  const state = await openDesk(page)
  await page.route(`**/tasks/${taskId}/claim`, async (route) => {
    state.task.status = 'ASSIGNED'
    state.task.version = 2
    state.task.assignee_id = '00000000-0000-4000-8000-000000000005'
    await route.fulfill({ json: state.task })
  })
  await page.getByRole('button', { name: '接管', exact: true }).click()
  await expect(page.getByText('请协助检查充电问题 · 已接管 · 版本 2')).toBeVisible()
  await expect(page.getByRole('button', { name: '接管', exact: true })).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})
