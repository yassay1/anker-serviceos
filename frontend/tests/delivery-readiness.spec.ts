import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { components } from '../src/api/schema'
import { fixture, ids } from './workspace-fixture'

type S = components['schemas']
type StreamHandle = {
  url: string, closed: boolean, onopen: (() => void) | null, onerror: (() => void) | null,
  onmessage: ((event: MessageEvent) => void) | null,
}
declare global { interface Window { testStreams: StreamHandle[], lateStreamMessage?: (event: MessageEvent) => void } }
const sequenceKey = `serviceos:event-sequence:${ids.tenant}:${ids.customer}:${ids.conversation}`

async function controlledStream(page: Page, stored?: string, denyStorage = false) {
  await page.addInitScript(({ stored, denyStorage, sequenceKey }) => {
    if (stored !== undefined) localStorage.setItem(sequenceKey, stored)
    if (denyStorage) {
      Storage.prototype.getItem = () => { throw new DOMException('Storage denied', 'SecurityError') }
      Storage.prototype.setItem = () => { throw new DOMException('Storage denied', 'SecurityError') }
    }
    window.testStreams = []
    class ControlledEventSource {
      onopen: (() => void) | null = null
      onerror: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      closed = false
      constructor(public url: string) {
        window.testStreams.push(this)
        setTimeout(() => { if (!this.closed) this.onopen?.() }, 0)
      }
      close() { this.closed = true }
    }
    window.EventSource = ControlledEventSource as unknown as typeof EventSource
  }, { stored, denyStorage, sequenceKey })
}

function event(sequence: number, summary = '正在查阅当前问题的授权资料。', stage = 'LOOKUP', conversationId = ids.conversation): S['EventRead'] {
  return { id: crypto.randomUUID(), conversation_id: conversationId, sequence, visibility: 'PUBLIC',
    type: 'agent.progress', data: { run_id: ids.device, stage, summary }, created_at: '2026-10-14T01:00:00Z' }
}
function specialistEvent(sequence: number, stage = 'RESULT_READY', summary = '初步假设（待核验）：可能是供电连接问题。', conversationId = ids.conversation): S['EventRead'] {
  return { id: crypto.randomUUID(), conversation_id: conversationId, sequence, visibility: 'PUBLIC',
    type: 'specialist.activity', data: { task_id: ids.second, specialist_run_id: ids.device, agent_type: 'DIAGNOSTIC',
      display_name: '诊断专家', stage, summary, certainty: stage === 'RESULT_READY' ? 'HYPOTHESIS' : 'NONE' },
    created_at: '2026-10-14T01:00:00Z' }
}
function replyDelta(sequence: number, messageId: string, partIndex: number, text: string): S['EventRead'] {
  return { id: crypto.randomUUID(), conversation_id: ids.conversation, sequence, visibility: 'PUBLIC',
    type: 'agent.reply.delta', data: { message_id: messageId, part_index: partIndex, text },
    created_at: '2026-10-14T01:00:00Z' }
}
async function emit(page: Page, value: unknown, lastEventId: string) {
  await page.evaluate(({ value, lastEventId }) => {
    window.testStreams.find(stream => !stream.closed)?.onmessage?.(new MessageEvent('message', { data: JSON.stringify(value), lastEventId }))
  }, { value, lastEventId })
}
async function settle(page: Page) {
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
}
async function expandAssistance(page: Page) {
  const details = page.locator('details.ui-ActionBar').first()
  await expect(details).toBeAttached()
  if (await details.count() && !(await details.evaluate(element => (element as HTMLDetailsElement).open))) {
    await details.locator('summary').click()
  }
}

for (const stored of ['-1', '1.5', '01', '1e3', '9007199254740993', 'Infinity']) {
  test(`delivery SSE: invalid persisted cursor ${stored} is ignored`, async ({ page }) => {
    await controlledStream(page, stored)
    await fixture(page, false)
    await page.goto('/support')
    await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => window.testStreams.find(stream => !stream.closed)?.url)).toContain('after=0')
    await emit(page, event(2), '2')
    await expect(page.getByRole('region', { name: '助手最新进度' })).toContainText('正在查阅当前问题的授权资料。')
    expect(await page.evaluate(key => localStorage.getItem(key), sequenceKey)).toBe('2')
  })
}

test('delivery SSE: duplicate, out-of-order and malformed events never regress or refresh snapshots', async ({ page }) => {
  await controlledStream(page, '8')
  await fixture(page, false)
  let reads = 0
  page.on('request', request => { if (request.url().includes('/messages?')) reads++ })
  await page.goto('/support')
  await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
  await emit(page, event(20), '20') // Internal visibility can legitimately account for 9..19.
  await expect(page.getByRole('region', { name: '助手最新进度' })).toContainText('正在查阅当前问题的授权资料。')
  await settle(page)
  const baseline = reads
  for (const [value, id] of [
    [event(20, '重复进度'), '20'], [event(19, '过时进度'), '19'], [event(21), '21.0'],
    [event(21), '9007199254740993'], [event(21), '22'], [event(21, '其他会话', 'LOOKUP', ids.second), '21'],
    [{ ...event(21, '内部推理不可见'), visibility: 'INTERNAL' }, '21'], [null, '21'],
  ] as [unknown, string][]) await emit(page, value, id)
  await page.evaluate(() => window.testStreams.find(stream => !stream.closed)?.onmessage?.(new MessageEvent('message', { data: '{not json', lastEventId: '21' })))
  await settle(page)
  expect(reads).toBe(baseline)
  expect(await page.evaluate(key => localStorage.getItem(key), sequenceKey)).toBe('20')
  await expect(page.getByText(/重复进度|过时进度|内部推理不可见|其他会话/)).toHaveCount(0)
  await expect(page.getByText(/丢失事件|漏事件/)).toHaveCount(0)
})

test('delivery SSE: storage exceptions do not disable streaming or deduplication', async ({ page }) => {
  await controlledStream(page, undefined, true)
  const state = await fixture(page, false)
  await page.goto('/support')
  await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
  await emit(page, event(7, '服务端已开始处理', 'RUNNING'), '7')
  await emit(page, event(6, '不能倒退', 'RUNNING'), '6')
  await expect(page.getByRole('region', { name: '助手最新进度' })).toContainText('服务端已开始处理')
  await expect(page.getByText('不能倒退')).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})

test('delivery SSE: approved reply deltas render incrementally without snapshot refetches', async ({ page }) => {
  await controlledStream(page)
  const state = await fixture(page, false)
  const messageId = crypto.randomUUID()
  let reads = 0
  page.on('request', request => { if (request.url().includes('/messages?')) reads++ })
  await page.goto('/support')
  await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
  await settle(page)
  const baseline = reads
  const first = replyDelta(70, messageId, 0, '我已核对这条消息')
  await emit(page, first, '70')
  await expect(page.locator('.streaming-message')).toContainText('我已核对这条消息')
  await emit(page, replyDelta(71, messageId, 1, '，请告诉我设备型号。'), '71')
  await expect(page.locator('.streaming-message')).toContainText('我已核对这条消息，请告诉我设备型号。')
  await settle(page)
  expect(reads).toBe(baseline)

  state.messages.push({ id: messageId, conversation_id: ids.conversation, author_kind: 'AGENT',
    author_display_name: '服务助手', visibility: 'PUBLIC', content: [{ type: 'text', text: '我已核对这条消息，请告诉我设备型号。' }],
    related_case_id: null, client_message_id: ids.device, created_at: '2026-10-14T01:01:00Z' })
  await emit(page, { ...event(72), type: 'message.created', data: { message_id: messageId, conversation_id: ids.conversation } }, '72')
  await expect(page.getByText('我已核对这条消息，请告诉我设备型号。', { exact: true })).toBeVisible()
  await expect(page.locator('.streaming-message')).toHaveCount(0)
  expect(state.unexpected).toEqual([])
})

test('delivery SSE: reconnect restores history, newest revision and messages without duplicating replies', async ({ page }) => {
  await controlledStream(page, '40')
  const state = await fixture(page, false)
  let history = [event(40, '等待所需的图片信息', 'WAITING_EVIDENCE')]
  await page.route('**/event-history?*', route => route.fulfill({ json: { items: history, next_after: history.at(-1)!.sequence } }))
  await page.goto('/support')
  await expect(page.getByRole('region', { name: '助手最新进度' })).toContainText('等待所需的图片信息')
  const original = await page.evaluate(() => window.testStreams.length)
  const reply: S['MessageRead'] = { ...state.messages[1], id: crypto.randomUUID(), content: [{ type: 'text', text: '断线期间保存的回复' }] }
  state.messages.push(reply, reply)
  state.document.revision = 3
  history = [event(55, '已完成本轮资料整理', 'COMPLETED')]
  await page.evaluate(() => window.testStreams.find(stream => !stream.closed)?.onerror?.())
  await expect(page.getByText('重连中，消息仍可查询', { exact: true })).toBeVisible()
  await page.evaluate(() => window.testStreams.find(stream => !stream.closed)?.onopen?.())
  await expect(page.getByText('交互卡修订 3', { exact: true })).toBeVisible()
  await expect(page.getByText('断线期间保存的回复', { exact: true })).toHaveCount(1)
  await expect(page.getByRole('region', { name: '助手最新进度' })).toContainText('已完成本轮资料整理')
  expect(await page.evaluate(() => window.testStreams.length)).toBe(original)
  expect(state.sent).toEqual([])
  expect(state.unexpected).toEqual([])
})

test('delivery SSE: history pagination cannot overwrite newer stream progress', async ({ page }) => {
  await controlledStream(page)
  await fixture(page, false)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const afters: string[] = []
  await page.route('**/event-history?*', async route => {
    const after = new URL(route.request().url()).searchParams.get('after')!
    afters.push(after)
    if (after === '0') return route.fulfill({ json: { items: Array.from({ length: 100 }, (_, index) => event(index + 1, '历史已开始', 'RUNNING')), next_after: 100 } })
    await gate
    return route.fulfill({ json: { items: [event(101, '旧的等待状态', 'WAITING_APPROVAL')], next_after: 101 } })
  })
  await page.goto('/support')
  await expect.poll(() => afters.length).toBe(2)
  await emit(page, event(110, '新的失败回执', 'FAILED'), '110')
  release()
  await settle(page)
  await expect(page.getByRole('region', { name: '助手最新进度' })).toContainText('新的失败回执')
  await expect(page.getByText('旧的等待状态')).toHaveCount(0)
  expect(afters).toEqual(['0', '100'])
})

test('delivery SSE: specialist identity and hypothesis restore from event history and remain separate from messages', async ({ page }) => {
  await controlledStream(page, '40')
  const state = await fixture(page, false)
  await page.route('**/event-history?*', route => route.fulfill({ json: {
    items: [specialistEvent(39, 'STARTED', '诊断专家已开始分析当前问题。'), specialistEvent(40)], next_after: 40,
  } }))
  await page.goto('/support')
  const activity = page.getByRole('region', { name: '诊断专家活动' })
  await expect(activity).toContainText('诊断专家 · 形成待核验假设')
  await expect(activity).toContainText('可能是供电连接问题')
  await expect(activity).toContainText('不是已确认的设备事实')
  await expect(page.locator('.message-list')).not.toContainText('可能是供电连接问题')
  await emit(page, specialistEvent(41, 'FAILED', '诊断专家本次分析未完成，服务助手将继续处理。'), '41')
  await expect(activity).toContainText('本次分析未完成')
  await emit(page, { ...specialistEvent(42, 'LOOKUP', '诊断专家正在查阅已批准的售后资料。'), visibility: 'INTERNAL' }, '42')
  await expect(activity).toContainText('本次分析未完成')
  await expect(activity).not.toContainText('正在查阅已批准的售后资料')
  expect(state.unexpected).toEqual([])
})

test('diagnostic question UI submits a versioned answer through the controlled action API', async ({ page }) => {
  const state = await fixture(page, false)
  state.document.components.unshift({
    id: 'diagnostic-question', type: 'QuestionForm',
    props: { title: '诊断专家需要补充的信息', body: '充电器指示灯是否亮起？' },
    actions: [{ action_id: 'submit-diagnostic-answer', intent: 'SUBMIT_DIAGNOSTIC_ANSWER',
      input_schema_ref: 'serviceos://ui-inputs/diagnostic-answer/v1' }],
    children: [], options: [],
    data_source: { kind: 'DIAGNOSTIC_TASK_VIEW', resource_id: ids.second, resource_version: 8,
      binding: 'question', question_revision: 2 },
  })
  await page.goto('/support')
  await page.getByLabel('你的回答').fill('灯没有亮')
  await page.getByRole('button', { name: '提交给诊断专家' }).click()
  await expect(page.getByRole('status').filter({ hasText: '回答已保存，诊断专家将继续分析。' })).toBeVisible()
  expect(state.actions).toHaveLength(1)
  expect(state.actions[0].action_id).toBe('submit-diagnostic-answer')
  expect(state.actions[0].input).toEqual({ task_version: 8, question_revision: 2, answer: '灯没有亮' })
  expect(state.sent).toEqual([])
  expect(state.unexpected).toEqual([])
})

test('delivery SSE: switching conversations closes and ignores late old handlers', async ({ page }) => {
  await controlledStream(page)
  const state = await fixture(page, false)
  state.conversations[1].status = 'ACTIVE'
  await page.goto('/support')
  await expect(page.getByText('实时更新已连接', { exact: true })).toBeVisible()
  await emit(page, event(5, '第一段会话进度', 'RUNNING'), '5')
  await page.evaluate(() => { window.lateStreamMessage = window.testStreams.find(stream => !stream.closed)?.onmessage ?? undefined })
  await page.locator('.conversation-selector summary').click()
  await page.getByRole('complementary', { name: '会话列表', exact: true }).getByRole('button', { name: /22222222/ }).click()
  await expect(page.getByText('第一段会话进度')).toHaveCount(0)
  await page.evaluate(value => window.lateStreamMessage?.(new MessageEvent('message', { data: JSON.stringify(value), lastEventId: '8' })), event(8, '延迟的旧进度'))
  await expect(page.getByText('延迟的旧进度')).toHaveCount(0)
  expect(await page.evaluate(() => window.testStreams.filter(stream => !stream.closed).length)).toBe(1)
  expect(await page.evaluate(key => localStorage.getItem(key), sequenceKey)).toBe('5')
})

test('delivery UI: only real message case references become customer case links', async ({ page }) => {
  const state = await fixture(page, false)
  state.messages[0].related_case_id = ids.second
  await page.route(`**/api/v1/cases/${ids.second}`, route => route.fulfill({ json: {
    id: ids.second, customer_id: ids.customer, problem_text: '已关联的充电问题', user_goal: '恢复稳定供电',
    status: 'WAITING_CUSTOMER', version: 3, created_at: '2026-10-14T01:00:00Z',
  } satisfies S['CaseRead'] }))
  await page.goto('/support')
  await expect(page.getByRole('link', { name: '已关联的充电问题', exact: true })).toHaveAttribute('href', `/cases/${ids.second}`)
  await page.getByText('服务目标与下一步', { exact: true }).click()
  await expect(page.getByText('恢复稳定供电', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '证据与处理记录' })).toHaveAttribute('href', `/cases/${ids.second}`)
  await expect(page.locator('.message-list-wrap .ui-document')).toHaveCount(1)
  await expect(page.locator('.context-panel .ui-document')).toHaveCount(0)
  await page.getByRole('button', { name: '填写回复', exact: true }).click()
  await expect(page.getByLabel('描述你的问题')).toBeFocused()
  expect(state.unexpected).toEqual([])
})

test('delivery UI: inaccessible associated cases show refusal rather than another case', async ({ page }) => {
  const state = await fixture(page, false)
  state.messages[0].related_case_id = ids.second
  await page.route(`**/api/v1/cases/${ids.second}`, route => route.fulfill({ status: 403, json: { detail: '当前账号不能查看此案例。' } }))
  await page.goto('/support')
  await expect(page.getByRole('alert')).toContainText('当前账号不能查看此案例。')
  await expect(page.getByRole('link', { name: '证据与处理记录' })).toHaveCount(0)
  await expect(page.getByLabel('描述你的问题')).toBeEnabled()
})

for (const invalid of ['unknown', 'props', 'null-components', 'duplicate', 'expired', 'stale-context', 'catalog', 'unsafe-action', 'internal'] as const) {
  test(`delivery UI: ${invalid} document falls back without exposing an action`, async ({ page }) => {
    const state = await fixture(page, false)
    const document = structuredClone(state.document) as unknown as Record<string, unknown>
    const cards = document.components as S['UIComponent'][]
    document.fallback_text = '请继续使用文字消息。'
    if (invalid === 'unknown') cards[0].type = 'RemoteHTML'
    if (invalid === 'props') (cards[0].props as Record<string, unknown>).body = { html: '<img src=x onerror=alert(1)>' }
    if (invalid === 'null-components') document.components = null
    if (invalid === 'duplicate') cards.push(cards[0])
    if (invalid === 'expired') document.expires_at = '2020-01-01T00:00:00Z'
    if (invalid === 'stale-context') cards[0].data_source.resource_version = 2
    if (invalid === 'catalog') document.catalog_version = 99
    if (invalid === 'unsafe-action') (cards[1].actions[0] as unknown as Record<string, unknown>).endpoint = 'https://untrusted.invalid'
    if (invalid === 'internal') { document.audience = 'STAFF'; document.visibility = 'INTERNAL'; document.fallback_text = '绝不能泄露的内部说明' }
    await page.route('**/ui-document/refresh', route => route.fulfill({ json: document }))
    await page.goto('/support')
    const region = page.getByRole('region', { name: '服务交互卡', exact: true })
    await expect(region.getByRole('button', { name: '刷新交互卡' })).toBeVisible()
    await expect(region.getByRole('button', { name: '请求人工协助' })).toHaveCount(0)
    await expect(page.getByText('绝不能泄露的内部说明')).toHaveCount(0)
    await expect(page.getByLabel('描述你的问题')).toBeEnabled()
    await expect(region.locator('img, script, iframe')).toHaveCount(0)
  })
}

test('delivery UI: an older revision cannot enable new actions after reconnect', async ({ page }) => {
  await controlledStream(page)
  const state = await fixture(page, false)
  await page.goto('/support')
  await expect(page.getByText('交互卡修订 2', { exact: true })).toBeVisible()
  await expandAssistance(page)
  state.document.revision = 1
  await emit(page, { ...event(10), type: 'ui.document.published' }, '10')
  await expect(page.getByRole('button', { name: '刷新交互卡' })).toBeVisible()
  await expect(page.getByRole('button', { name: '请求人工协助' })).toHaveCount(0)
  state.document.revision = 3
  await page.getByRole('button', { name: '刷新交互卡' }).click()
  await expect(page.getByText('交互卡修订 3', { exact: true })).toBeVisible()
  await expandAssistance(page)
  await expect(page.getByRole('button', { name: '请求人工协助' })).toBeEnabled()
})

test('delivery UI: expiry disables the displayed action without waiting for snapshot polling', async ({ page }) => {
  await controlledStream(page)
  const state = await fixture(page, false)
  state.document.expires_at = new Date(Date.now() + 10_000).toISOString()
  await page.goto('/support')
  await expandAssistance(page)
  await expect(page.getByRole('button', { name: '请求人工协助' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '刷新交互卡' })).toBeVisible({ timeout: 12_000 })
  await expect(page.getByRole('button', { name: '请求人工协助' })).toHaveCount(0)
})

test('delivery UI: a failed refresh removes stale actions but keeps text messaging available', async ({ page }) => {
  await controlledStream(page)
  await fixture(page, false)
  await page.goto('/support')
  await expandAssistance(page)
  await expect(page.getByRole('button', { name: '请求人工协助' })).toBeEnabled()
  await page.route('**/ui-document/refresh', route => route.fulfill({ status: 403, json: { detail: '当前身份不能读取交互卡。' } }))
  await emit(page, { ...event(12), type: 'ui.document.published' }, '12')
  await expect(page.getByRole('alert')).toContainText('当前身份不能读取交互卡。')
  await expect(page.getByRole('button', { name: '请求人工协助' })).toHaveCount(0)
  await expect(page.getByLabel('描述你的问题')).toBeEnabled()
})

test('delivery UI: staff catalog preserves evidence, handoff and single-node real progress semantics', async ({ page }) => {
  const state = await fixture(page)
  const source = { kind: 'CASE_VIEW', resource_id: ids.second, resource_version: 2, binding: 'summary' } as const
  state.document.components = [
    { id: 'summary', type: 'CaseSummaryCard', props: { title: '服务问题', body: '需要确认接口表现。', status: 'WAITING_CUSTOMER', source: '客户陈述', verification: 'CANDIDATE' }, actions: [], children: [], data_source: source },
    { id: 'evidence', type: 'EvidenceSummary', props: { title: '线材观察', body: '暂不能作为设备事实。', source: '已撤销的观察', verification: 'RETRACTED' }, actions: [], children: [], data_source: { ...source, binding: 'evidence' } },
    { id: 'handoff', type: 'HandoffSummary', props: { title: '协作任务', body: '等待授权客服接管。', status: 'OPEN' }, actions: [], children: [], data_source: { ...source, kind: 'TASK_VIEW', binding: 'handoff' } },
    { id: 'progress', type: 'ProgressTimeline', props: { title: '实际任务状态', body: '任务尚在等待审批。', status: 'WAITING_APPROVAL' }, actions: [], children: [], data_source: { ...source, kind: 'TASK_VIEW', binding: 'progress' } },
  ]
  await page.goto('/desk')
  const cards = page.getByRole('region', { name: '客服交互卡', exact: true })
  await expect(cards.locator('.ui-CaseSummaryCard')).toContainText('待核验')
  await expect(cards.locator('.ui-EvidenceSummary')).toContainText('已撤销')
  await expect(cards.locator('.ui-HandoffSummary')).toContainText('待处理')
  await expect(cards.locator('.ui-timeline li')).toHaveCount(1)
  await expect(cards.locator('.ui-timeline')).toContainText('待审批')
  await expect(cards.getByRole('link', { name: '查看案例与证据' }).first()).toHaveAttribute('href', `/cases/${ids.second}`)
  await expect(cards.getByText(/已完成|已解决/)).toHaveCount(0)
})

test('delivery UI: catalog 4 customer case progress keeps the approved card actions available', async ({ page }) => {
  const state = await fixture(page, false)
  state.document.catalog_version = 4
  state.document.components.unshift({
    id: 'case-progress', type: 'ProgressTimeline',
    props: { title: '服务进度', body: '案例正在等待补充信息。', status: 'WAITING_CUSTOMER' },
    actions: [], children: [],
    data_source: { kind: 'CASE_VIEW', binding: 'progress', resource_id: ids.second, resource_version: 2 },
  })
  await page.goto('/support')
  const card = page.getByRole('region', { name: '服务交互卡', exact: true })
  await expect(card.locator('.ui-ProgressTimeline')).toContainText('服务进度')
  await expandAssistance(page)
  await expect(card.getByRole('button', { name: '请求人工协助' })).toBeEnabled()
  await card.getByRole('button', { name: '请求人工协助' }).click()
  await expect(card.getByText('人工协助请求已保存。')).toBeVisible()
  expect(state.actions).toHaveLength(1)
  expect(state.actions[0].action_id).toBe('request-human-assistance')
  expect(state.unexpected).toEqual([])
})

test('delivery UI: customer metric uses the bounded curated chart payload', async ({ page }) => {
  const state = await fixture(page, false)
  state.document.catalog_version = 3
  state.document.components.push({ id: 'metric', type: 'KnowledgeMetricChart',
    props: { title: '加热功能的额外电量消耗估算', body: '来自已发布知识条目的估算。' }, actions: [], children: [],
    data_source: { kind: 'AGENT_RUN_VIEW', binding: 'metric', resource_id: ids.device, resource_version: 1 },
    chart: { metric_id: 'heating-extra-battery', chart_type: 'BAR', x_axis_label: '加热时长（分钟）',
      y_axis_label: '额外电量消耗', unit: '%',
      points: [{ label: '5 分钟', value: 10 }, { label: '10 分钟', value: 20 }, { label: '15 分钟', value: 30 }],
      source_label: '已发布知识条目', source_version: '0123456789abcdef', note: '近似估算，不是个人设备遥测。' },
  })
  await page.goto('/support')
  const card = page.locator('.ui-KnowledgeMetricChart')
  await expect(card.getByRole('img', { name: '额外电量消耗柱状图' })).toBeVisible()
  await expect(card.locator('.ui-chart-bar')).toHaveCount(3)
  await expect(card.locator('.ui-chart-source')).toContainText('0123456789abcdef')
  await expect(page.getByLabel('描述你的问题')).toBeEnabled()
})

test('delivery UI: staff case process flow displays source states and is staff-only', async ({ page }) => {
  const state = await fixture(page)
  state.document.catalog_version = 3
  state.document.components = [{ id: 'process-flow', type: 'CaseProcessFlow',
    props: { title: '案例办理流程', body: '节点状态来自当前案例和任务。' }, actions: [], children: [],
    data_source: { kind: 'CASE_VIEW', binding: 'process_flow', resource_id: ids.second, resource_version: 2 },
    flow: { nodes: [
      { id: 'case', label: '服务案例', status: 'WAITING', detail: '当前案例状态：WAITING_CUSTOMER',
        resource_kind: 'CASE_VIEW', resource_id: ids.second, resource_version: 2 },
      { id: 'human-task', label: '人工协作', status: 'IN_PROGRESS', detail: '当前任务状态：ASSIGNED',
        resource_kind: 'TASK_VIEW', resource_id: ids.device, resource_version: 1 },
    ], edges: [{ source: 'case', target: 'human-task' }] },
  }]
  await page.goto('/desk')
  const card = page.locator('.ui-CaseProcessFlow')
  await expect(card.getByRole('img', { name: '案例办理流程图' })).toBeVisible()
  await expect(card.locator('.ui-flow-details')).toContainText('当前任务状态：ASSIGNED')
  expect(await card.locator('.ui-flow').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
})

test('delivery UI: customer document cannot render a staff process flow', async ({ page }) => {
  const state = await fixture(page, false)
  state.document.catalog_version = 3
  state.document.components = [{ id: 'process-flow', type: 'CaseProcessFlow',
    props: { title: '案例办理流程', body: '内部流程。' }, actions: [], children: [],
    data_source: { kind: 'CASE_VIEW', binding: 'process_flow', resource_id: ids.second, resource_version: 2 },
    flow: { nodes: [{ id: 'case', label: '服务案例', status: 'WAITING', detail: '等待客户补充信息。',
      resource_kind: 'CASE_VIEW', resource_id: ids.second, resource_version: 2 }], edges: [] },
  }]
  await page.goto('/support')
  await expect(page.getByRole('button', { name: '刷新交互卡' })).toBeVisible()
  await expect(page.locator('.ui-CaseProcessFlow')).toHaveCount(0)
})

test('delivery UI: altered metric values fall back without rendering SVG data', async ({ page }) => {
  const state = await fixture(page, false)
  state.document.catalog_version = 3
  state.document.components.push({ id: 'metric', type: 'KnowledgeMetricChart',
    props: { title: '加热估算', body: '估算说明。' }, actions: [], children: [],
    data_source: { kind: 'AGENT_RUN_VIEW', binding: 'metric', resource_id: ids.device, resource_version: 1 },
    chart: { metric_id: 'heating-extra-battery', chart_type: 'BAR', x_axis_label: '加热时长（分钟）',
      y_axis_label: '额外电量消耗', unit: '%',
      points: [{ label: '5 分钟', value: 999 }, { label: '10 分钟', value: 20 }, { label: '15 分钟', value: 30 }],
      source_label: '已发布知识条目', source_version: '0123456789abcdef', note: '近似估算。' },
  })
  await page.goto('/support')
  await expect(page.getByRole('button', { name: '刷新交互卡' })).toBeVisible()
  await expect(page.locator('.ui-chart')).toHaveCount(0)
  await expect(page.getByLabel('描述你的问题')).toBeEnabled()
})

test('delivery UI: catalog types are distinct, text remains inert, and mobile cards are accessible', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const state = await fixture(page, false)
  const source = state.document.components[0].data_source
  state.document.components.unshift({ id: 'risk', type: 'RiskAlert', props: { title: '操作前请注意安全', body: '若设备异常发热，请停止排查并说明情况。' }, actions: [], children: [], data_source: source })
  state.document.components[1].props.body = '<img src=x onerror=alert(1)> https://example.invalid 请直接描述线材情况。'
  await page.goto('/support')
  const cards = page.locator('.conversation-ui')
  await expect(cards.locator('.ui-card').first()).toHaveClass(/ui-RiskAlert/)
  await expect(cards.locator('.ui-QuestionForm')).toContainText('<img src=x onerror=alert(1)>')
  await expect(cards.locator('img, iframe, a[href^="https:"]')).toHaveCount(0)
  await expect(cards.locator('.ui-ActionBar')).toHaveCount(1)
  await page.getByRole('button', { name: '填写回复' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('描述你的问题')).toBeFocused()
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.locator('.message-list-wrap').evaluate(element => { element.scrollTop = 0 })
  await page.screenshot({ path: testInfo.outputPath('delivery-support-mobile.png'), fullPage: true })
})


function withChoices(state: Awaited<ReturnType<typeof fixture>>, options: unknown) {
  const document = structuredClone(state.document) as unknown as Record<string, unknown>
  document.catalog_version = 2
  const cards = document.components as (S['UIComponent'] & { options?: unknown })[]
  cards.push({ id: 'agent-choice', type: 'ChoiceGroup',
    props: { title: '下一步需要的信息', body: '指示灯现在是什么状态？' },
    actions: [], children: [], options: options as { label: string, value: string }[],
    data_source: { kind: 'CONVERSATION_VIEW', binding: 'assistance', resource_id: ids.conversation, resource_version: 3 } })
  return document
}

test('delivery UI: clicking a choice sends it as an ordinary customer message', async ({ page }) => {
  const state = await fixture(page, false)
  await page.route('**/ui-document/refresh', route => route.fulfill({
    json: withChoices(state, [{ label: '指示灯完全不亮', value: 'no-light' }, { label: '指示灯常亮', value: 'steady' }]),
  }))
  await page.goto('/support')
  const region = page.getByRole('region', { name: '服务交互卡', exact: true })
  await expandAssistance(page)
  const choices = region.getByRole('group', { name: '下一步需要的信息' })
  await expect(choices.getByRole('button')).toHaveCount(2)
  await choices.getByRole('button', { name: '指示灯完全不亮' }).click()
  await expect(region.getByRole('status')).toHaveText('已发送：指示灯完全不亮')
  expect(state.sent.at(-1)).toMatchObject({
    content: [{ type: 'text', text: '指示灯完全不亮' }], visibility: 'PUBLIC', related_case_id: null,
  })
  expect(state.sent.at(-1)?.client_message_id).toMatch(/^[0-9a-f-]{36}$/)
  // The choice path must not touch the assistance action surface.
  await expandAssistance(page)
  expect(await region.getByRole('button', { name: '请求人工协助' }).count()).toBe(1)
})

test('delivery UI: an uncertain choice retries with its original message id', async ({ page }) => {
  const state = await fixture(page, false)
  const attempts: string[] = []
  await page.route('**/ui-document/refresh', route => route.fulfill({
    json: withChoices(state, [{ label: '指示灯完全不亮', value: 'no-light' }, { label: '指示灯常亮', value: 'steady' }]),
  }))
  await page.route('**/api/v1/conversations/*/messages', async route => {
    attempts.push((route.request().postDataJSON() as S['SendMessage']).client_message_id)
    if (attempts.length === 1) return route.fulfill({ status: 503, json: { detail: '暂时不可用' } })
    await route.fallback()
  })
  await page.goto('/support')
  const region = page.getByRole('region', { name: '服务交互卡', exact: true })
  await expandAssistance(page)
  await region.getByRole('button', { name: '指示灯完全不亮' }).click()
  await expect(region.getByRole('status')).toContainText('发送结果未确认')
  await expect(region.getByRole('button', { name: '指示灯常亮' })).toBeDisabled()
  await page.getByRole('button', { name: '用原消息重试' }).click()
  await expect.poll(() => state.sent.length).toBe(1)
  expect(attempts).toHaveLength(2)
  expect(attempts[1]).toBe(attempts[0])
  expect(state.sent[0].client_message_id).toBe(attempts[0])
})

test('delivery UI: choices disappear at expiry and the text path stays available', async ({ page }) => {
  const state = await fixture(page, false)
  const document = withChoices(state, [{ label: '指示灯完全不亮', value: 'no-light' }, { label: '指示灯常亮', value: 'steady' }])
  document.expires_at = new Date(Date.now() + 4000).toISOString()
  await page.route('**/ui-document/refresh', route => route.fulfill({ json: document }))
  await page.goto('/support')
  const region = page.getByRole('region', { name: '服务交互卡', exact: true })
  await expandAssistance(page)
  await expect(region.getByRole('button', { name: '指示灯完全不亮' })).toBeEnabled()
  // Expiry is handled like every other unsupported document: the card falls back rather than
  // offering a stale write, and the message path never depends on it.
  await expect(region.getByRole('button', { name: '刷新交互卡' })).toBeVisible({ timeout: 8000 })
  await expect(region.locator('.ui-choices')).toHaveCount(0)
  await expect(page.getByLabel('描述你的问题')).toBeEnabled()
})

test('delivery UI: an archived conversation disables every card control and the composer', async ({ page }) => {
  const state = await fixture(page, false)
  state.conversations[0].status = 'ARCHIVED'
  await page.goto('/support')
  const region = page.getByRole('region', { name: '服务交互卡', exact: true })
  await expandAssistance(page)
  await expect(region.getByRole('button', { name: '请求人工协助' })).toBeDisabled()
  await expect(region.getByRole('button', { name: '填写回复' })).toBeDisabled()
  await expect(page.getByLabel('描述你的问题')).toBeDisabled()
  // Choices reuse that same activity gate, so no stale choice can be sent from an archive.
  await expect(page.locator('.ui-choices button:not([disabled])')).toHaveCount(0)
})

for (const [name, options] of [
  ['empty', []],
  ['single', [{ label: '只有一个', value: 'only' }]],
  ['unsafe-label', [{ label: '<img src=x onerror=alert(1)>', value: 'ok' }, { label: '乙', value: 'ok-2' }]],
  ['bad-slug', [{ label: '甲', value: 'Not A Slug' }, { label: '乙', value: 'ok' }]],
  ['duplicate', [{ label: '重复', value: 'a' }, { label: '重复', value: 'b' }]],
  ['with-endpoint', [{ label: '甲', value: 'ok', endpoint: '/api/v1/anything' }, { label: '乙', value: 'ok-2' }]],
] as const) {
  test(`delivery UI: ${name} choices fall back without offering a click`, async ({ page }) => {
    const state = await fixture(page, false)
    await page.route('**/ui-document/refresh', route => route.fulfill({ json: withChoices(state, options) }))
    await page.goto('/support')
    const region = page.getByRole('region', { name: '服务交互卡', exact: true })
    await expect(region.getByRole('button', { name: '刷新交互卡' })).toBeVisible()
    await expect(region.locator('.ui-choices')).toHaveCount(0)
    await expect(region.locator('img, script, iframe')).toHaveCount(0)
    await expect(page.getByLabel('描述你的问题')).toBeEnabled()
  })
}
