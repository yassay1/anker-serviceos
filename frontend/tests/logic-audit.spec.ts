import { expect, test, type Page } from '@playwright/test'
import type { components } from '../src/api/schema'
import { fixture, ids } from './workspace-fixture'

type S = components['schemas']

function assistanceDocument(document: S['UIDocumentRead']) {
  document.components = [{ id: 'assistance', type: 'ActionBar',
    props: { title: '人工协助', body: '保存请求后由客服接续。' },
    actions: [{ action_id: 'request-human-assistance', intent: 'REQUEST_ASSISTANCE',
      input_schema_ref: 'serviceos://ui-inputs/assistance-request/v1' }], children: [],
    data_source: { kind: 'CONVERSATION_VIEW', resource_id: ids.conversation, resource_version: 3, binding: 'assistance' } }]
}

async function expandAssistance(page: Page) {
  const retry = page.getByRole('button', { name: '用原请求重试', exact: true })
  const submit = page.getByRole('button', { name: '提交协助请求', exact: true })
  if (await retry.isVisible() || await submit.isVisible()) return
  const trigger = page.getByRole('button', { name: '请求真人协助', exact: true })
  await retry.or(submit).or(trigger).waitFor({ state: 'visible' })
  if (await trigger.isVisible() && await trigger.isEnabled()) await trigger.click()
}

test('logic audit: oldest-first pagination reaches the latest saved reply', async ({ page }) => {
  const state = await fixture(page, false)
  const messages: S['MessageRead'][] = Array.from({ length: 115 }, (_, index) => ({
    ...state.messages[0], id: crypto.randomUUID(), created_at: new Date(Date.UTC(2026, 9, 14, 1, 0, index)).toISOString(),
    content: [{ type: 'text', text: index === 114 ? '长会话中的最新回复' : `历史消息 ${index + 1}` }],
  }))
  await page.route('**/api/v1/conversations/*/messages?*', route => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor')
    const start = cursor ? messages.findIndex(message => message.id === cursor) + 1 : 0
    const items = messages.slice(start, start + 50)
    return route.fulfill({ json: { items, next_cursor: start + 50 < messages.length ? items.at(-1)!.id : null } })
  })
  await page.goto('/support')
  await expect(page.getByText('长会话中的最新回复', { exact: true })).toBeVisible()
  const reply = await page.getByText('长会话中的最新回复', { exact: true }).boundingBox()
  const thread = await page.locator('.message-list-wrap').boundingBox()
  expect(reply!.y + reply!.height).toBeLessThanOrEqual(thread!.y + thread!.height + 1)
  await expect(page.getByText('历史消息 1', { exact: true })).toHaveCount(1)
  await expect(page.getByRole('button', { name: '加载更早消息', exact: true })).toHaveCount(0)
  await page.locator('.message-list-wrap').evaluate(element => { element.scrollTop = 0 })
  messages.push({ ...messages[114], id: crypto.randomUUID(), created_at: '2026-10-14T01:02:00Z', content: [{ type: 'text', text: '阅读历史时到达的新回复' }] })
  await expect(page.getByText('阅读历史时到达的新回复', { exact: true })).toHaveCount(1, { timeout: 12_000 })
  expect(await page.locator('.message-list-wrap').evaluate(element => element.scrollTop)).toBe(0)
})

test('logic audit: another logged-in actor cannot inherit the previous draft', async ({ page }) => {
  const state = await fixture(page)
  await page.goto('/desk')
  await page.getByLabel('回复客户').fill('上一位客服尚未发送的内部信息')
  await page.getByRole('button', { name: '内部备注', exact: true }).click()
  state.actor.actor_id = crypto.randomUUID()
  state.actor.display_name = '新登录的客服'
  await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')))
  await expect(page.getByText('新登录的客服', { exact: false })).toBeVisible()
  await expect(page.getByLabel('回复客户')).toHaveValue('')
  await expect(page.getByRole('button', { name: '内部备注', exact: true })).toHaveAttribute('aria-pressed', 'false')
})

test('logic audit: unknown UI result keeps the same request across a new revision', async ({ page }) => {
  const state = await fixture(page, false)
  assistanceDocument(state.document)
  const bodies: S['UIActionRequest'][] = []
  await page.route('**/ui-actions', async route => {
    const body = route.request().postDataJSON() as S['UIActionRequest']
    bodies.push(body)
    if (bodies.length === 1) {
      state.document.revision++
      return route.abort('failed')
    }
    await route.fulfill({ json: { client_action_id: body.client_action_id, status: 'ACCEPTED', task_id: ids.second, replayed: true } satisfies S['UIActionResult'] })
  })
  await page.goto('/support')
  const card = page.locator('.customer-assistance .ui-document')
  await expandAssistance(page)
  await card.getByRole('button', { name: '提交协助请求', exact: true }).click()
  await expect(card.getByRole('button', { name: '用原请求重试', exact: true })).toBeVisible()
  await expect(card.getByLabel('请求原因')).toBeDisabled()
  await card.getByRole('button', { name: '用原请求重试', exact: true }).click()
  await expect(card.getByRole('status')).toHaveText('人工协助请求已存在。')
  expect(bodies).toHaveLength(2)
  expect(bodies[1]).toEqual(bodies[0])
})

test('logic audit: rejected stale UI refreshes without replay and permits a fresh request', async ({ page }) => {
  const state = await fixture(page, false)
  assistanceDocument(state.document)
  const bodies: S['UIActionRequest'][] = []
  await page.route('**/ui-actions', async route => {
    const body = route.request().postDataJSON() as S['UIActionRequest']
    bodies.push(body)
    if (bodies.length === 1) {
      state.document.revision++
      return route.fulfill({ status: 409, json: { detail: 'UI 版本已更新，请刷新卡片后重试。' } })
    }
    await route.fulfill({ json: { client_action_id: body.client_action_id, status: 'ACCEPTED', task_id: ids.second, replayed: false } satisfies S['UIActionResult'] })
  })
  await page.goto('/support')
  const card = page.locator('.customer-assistance .ui-document')
  await expandAssistance(page)
  await card.getByRole('button', { name: '提交协助请求', exact: true }).click()
  await expect(card.getByRole('alert')).toHaveText('UI 版本已更新，请刷新卡片后重试。')
  expect(bodies).toHaveLength(1)
  await expandAssistance(page)
  await card.getByRole('button', { name: '提交协助请求', exact: true }).click()
  await expect(card.getByRole('status')).toHaveText('人工协助请求已保存。')
  expect(bodies[1].revision).toBe(3)
  expect(bodies[1].client_action_id).not.toBe(bodies[0].client_action_id)
})

test('logic audit: archived conversations expose no active collaboration commands', async ({ page }) => {
  const state = await fixture(page)
  state.conversations[0].status = 'ARCHIVED'
  await page.goto('/desk')
  await page.getByRole('button', { name: '人工协作与审批', exact: true }).click()
  await expect(page.getByRole('button', { name: '发送回复', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '切换策略', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '放入回复框', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '忽略建议', exact: true })).toBeDisabled()
})

test('logic audit: customer assistance has one idempotent submission entry', async ({ page }) => {
  const state = await fixture(page, false)
  assistanceDocument(state.document)
  await page.goto('/support')
  await expect(page.getByRole('button', { name: '请求真人协助', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '请求真人协助', exact: true })).toHaveCount(1)
})

for (const navigation of ['conversation', 'devices', 'reload'] as const) {
  test(`logic audit: uncertain assistance survives ${navigation}`, async ({ page }) => {
    const state = await fixture(page, false)
    state.conversations[1].status = 'ACTIVE'
    assistanceDocument(state.document)
    const bodies: S['UIActionRequest'][] = []
    await page.route('**/ui-actions', async route => {
      const body = route.request().postDataJSON() as S['UIActionRequest']
      bodies.push(body)
      if (bodies.length === 1) return route.abort('failed')
      return route.fulfill({ json: { client_action_id: body.client_action_id, status: 'ACCEPTED', task_id: ids.second, replayed: true } satisfies S['UIActionResult'] })
    })
    await page.goto(`/support?conversation=${ids.conversation}`)
    const card = page.locator('.customer-assistance .ui-document')
    await expandAssistance(page)
    await card.getByRole('button', { name: '提交协助请求', exact: true }).click()
    await expect(card.getByRole('button', { name: '用原请求重试', exact: true })).toBeVisible()
    if (navigation === 'conversation') {
      const list = page.getByRole('complementary', { name: '会话列表', exact: true })
      await list.getByRole('button', { name: /22222222/ }).click()
      await list.getByRole('button', { name: /11111111/ }).click()
    } else if (navigation === 'devices') {
      await page.goto(`/devices/${ids.device}`)
      await page.goto(`/support?conversation=${ids.conversation}`)
    } else await page.reload()
    await expandAssistance(page)
    await expect(card.getByRole('button', { name: '用原请求重试', exact: true })).toBeVisible()
    expect(bodies).toHaveLength(1)
    await card.getByRole('button', { name: '用原请求重试', exact: true }).click()
    await expect(card.getByRole('status')).toHaveText('人工协助请求已存在。')
    expect(bodies[1]).toEqual(bodies[0])
  })
}

test('logic audit: a late receipt cannot erase a newer uncertain request', async ({ page }) => {
  const state = await fixture(page, false)
  assistanceDocument(state.document)
  const bodies: S['UIActionRequest'][] = []
  let releaseFirst!: () => void
  const firstGate = new Promise<void>(resolve => { releaseFirst = resolve })
  await page.route('**/ui-actions', async route => {
    const body = route.request().postDataJSON() as S['UIActionRequest']
    bodies.push(body)
    const number = bodies.length
    if (number === 1) await firstGate
    if (number === 3) return route.abort('failed')
    return route.fulfill({ json: { client_action_id: body.client_action_id, status: 'ACCEPTED', task_id: ids.second, replayed: number !== 1 } satisfies S['UIActionResult'] })
  })
  const navigateWithinApp = async (path: string) => {
    await page.evaluate(nextPath => {
      window.history.pushState(null, '', nextPath)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, path)
    await page.waitForURL(`**${path}`)
    await page.locator(path.startsWith('/devices/') ? '.devices-page' : '.support-view').waitFor()
  }
  const returnToSupport = async () => {
    await navigateWithinApp(`/devices/${ids.device}`)
    await navigateWithinApp('/support')
  }
  await page.goto('/support')
  const card = page.locator('.customer-assistance .ui-document')
  await expandAssistance(page)
  await card.getByRole('button', { name: '提交协助请求', exact: true }).click()
  await expect.poll(() => bodies.length).toBe(1)
  await returnToSupport()
  await card.getByRole('button', { name: '用原请求重试', exact: true }).click()
  await expect(card.getByRole('status')).toHaveText('人工协助请求已存在。')
  await returnToSupport()
  await expandAssistance(page)
  await card.getByRole('button', { name: '提交协助请求', exact: true }).click()
  await expect(card.getByRole('button', { name: '用原请求重试', exact: true })).toBeVisible()
  expect(bodies[2].client_action_id).not.toBe(bodies[0].client_action_id)
  const oldResponse = page.waitForResponse(response => response.url().endsWith('/ui-actions') && response.request().postDataJSON().client_action_id === bodies[0].client_action_id)
  releaseFirst()
  await (await oldResponse).finished()
  // Let the fetch receipt handlers finish before testing recovery after reload.
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  await page.reload()
  await expandAssistance(page)
  await expect(card.getByRole('button', { name: '用原请求重试', exact: true })).toBeVisible()
  await card.getByRole('button', { name: '用原请求重试', exact: true }).click()
  await expect(card.getByRole('status')).toHaveText('人工协助请求已存在。')
  expect(bodies[3]).toEqual(bodies[2])
})
