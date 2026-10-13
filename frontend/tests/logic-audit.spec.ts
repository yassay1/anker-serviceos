import { expect, test } from '@playwright/test'
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
  await expect(page.getByText('历史消息 1', { exact: true })).toHaveCount(1)
  await expect(page.getByRole('button', { name: '加载更早消息', exact: true })).toHaveCount(0)
})

test('logic audit: another logged-in actor cannot inherit the previous draft', async ({ page }) => {
  const state = await fixture(page)
  await page.goto('/desk')
  await page.getByLabel('回复客户').fill('上一位客服尚未发送的内部信息')
  await page.getByLabel('仅客服可见的内部备注').check()
  state.actor.actor_id = crypto.randomUUID()
  state.actor.display_name = '新登录的客服'
  await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')))
  await expect(page.getByText('新登录的客服', { exact: false })).toBeVisible()
  await expect(page.getByLabel('回复客户')).toHaveValue('')
  await expect(page.getByLabel('仅客服可见的内部备注')).not.toBeChecked()
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
  const card = page.getByRole('region', { name: '服务交互卡', exact: true })
  await card.getByRole('button', { name: '请求人工协助', exact: true }).click()
  await expect(page.getByText('交互卡修订 3', { exact: true })).toBeVisible()
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
  const card = page.getByRole('region', { name: '服务交互卡', exact: true })
  await card.getByRole('button', { name: '请求人工协助', exact: true }).click()
  await expect(page.getByText('交互卡修订 3', { exact: true })).toBeVisible()
  await expect(card.getByRole('alert')).toHaveText('UI 版本已更新，请刷新卡片后重试。')
  expect(bodies).toHaveLength(1)
  await card.getByRole('button', { name: '请求人工协助', exact: true }).click()
  await expect(card.getByRole('status')).toHaveText('人工协助请求已保存。')
  expect(bodies[1].revision).toBe(3)
  expect(bodies[1].client_action_id).not.toBe(bodies[0].client_action_id)
})

test('logic audit: archived conversations expose no active collaboration commands', async ({ page }) => {
  const state = await fixture(page)
  state.conversations[0].status = 'ARCHIVED'
  await page.goto('/desk')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '切换策略', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeDisabled()
})
