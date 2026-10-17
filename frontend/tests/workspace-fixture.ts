import type { Page } from '@playwright/test'
import type { components } from '../src/api/schema'

type S = components['schemas']
export const ids = {
  conversation: '11111111-1111-4111-8111-111111111111',
  second: '22222222-2222-4222-8222-222222222222',
  device: '33333333-3333-4333-8333-333333333333',
  customer: '44444444-4444-4444-8444-444444444444',
  tenant: '55555555-5555-4555-8555-555555555555',
}
const createdAt = '2026-10-14T01:00:00Z'

export async function fixture(page: Page, staff = true) {
  const actor: S['ActorRead'] = { actor_id: staff ? '66666666-6666-4666-8666-666666666666' : ids.customer,
    tenant_id: ids.tenant, kind: staff ? 'STAFF' : 'CUSTOMER', role: staff ? 'STAFF' : null,
    display_name: staff ? '协作测试客服' : '服务测试客户' }
  const conversation: S['ConversationRead'] = { id: ids.conversation, customer_id: ids.customer,
    title: '充电设备服务咨询', status: 'ACTIVE', collaboration_mode: 'CO_SERVICE', reply_policy: 'AI_REVIEW_REQUIRED', version: 3, created_at: createdAt }
  const state = {
    conversations: [conversation, { ...conversation, id: ids.second, status: 'ARCHIVED' }],
    messages: [{ id: ids.second, conversation_id: ids.conversation, author_kind: 'CUSTOMER', author_display_name: '客户', visibility: 'PUBLIC',
      content: [{ type: 'text', text: '充电宝连接后供电不稳定，需要重新插拔才有反应。' }],
      client_message_id: null, related_case_id: null, created_at: createdAt },
      { id: ids.device, conversation_id: ids.conversation, author_kind: 'STAFF', author_display_name: '客服', visibility: 'PUBLIC',
        content: [{ type: 'text', text: '收到，我们在这段会话继续处理。请补充充电线材与适配器的信息。' }],
        client_message_id: null, related_case_id: null, created_at: createdAt }] as S['MessageRead'][],
    sent: [] as S['SendMessage'][], unexpected: [] as string[],
    actions: [] as S['UIActionRequest'][],
    proposals: [] as S['ProposalRead'][],
    replyDrafts: [] as S['StaffReplyDraftRead'][],
    assistance: [] as S['CustomerAssistanceRead'][],
  }
  const device: S['DeviceRead'] = { id: ids.device, customer_id: ids.customer, model: 'Anker 737',
    serial_number: 'PRIVATE-SERIAL-0921', identity_status: 'UNVERIFIED', revision: 2, created_at: createdAt,
    verified_facts: [{ id: ids.second, fact_key: 'charging_watts', value: 65,
      source: '人工测量记录', source_case_id: null, revision: 1,
      verified_by: '测试审核员', verified_at: createdAt, archived_at: null }] }
  const history: S['CaseRead'][] = [{ id: ids.second, customer_id: ids.customer,
    problem_text: '充电接口不稳定', user_goal: '恢复稳定充电', status: 'WAITING_CUSTOMER', version: 2, created_at: createdAt }]
  const proposal: S['ProposalRead'] = { id: ids.second, conversation_id: ids.conversation,
    proposal_type: 'REPLY', payload: { summary: '建议补充充电线材信息。' }, status: 'DRAFT', created_at: createdAt }
  state.proposals.push(proposal)
  const summary: S['DeskCaseSummary'] = { case: history[0], device_ids: [ids.device], facts: [
    { label: '问题描述', value: '充电接口连接后供电不稳定', source: '客户陈述', verification: 'CANDIDATE' },
  ] }
  const document: S['UIDocumentRead'] = { ui_id: ids.device, revision: 2, schema_version: 1, catalog_version: 1,
    audience: staff ? 'STAFF' : 'CUSTOMER', visibility: staff ? 'INTERNAL' : 'PUBLIC', surface: staff ? 'DESK_PANEL' : 'SUPPORT_PANEL',
    status: 'ACTIVE', components: [{ id: 'next', type: 'QuestionForm', props: { title: '下一步需要的信息', body: '请描述正在使用的充电线材和适配器。' }, actions: [], children: [], data_source: { kind: "CONVERSATION_VIEW", binding: "collaboration", resource_id: ids.conversation, resource_version: 3 } }],
    created_at: createdAt, expires_at: null, source_agent_run_id: null, fallback_text: '请继续使用文字消息。' }
  if (!staff) document.components.push({ id: 'request-assistance', type: 'ActionBar',
    props: { title: '需要真人协助？', body: '请求会创建人工任务；你仍可继续发送文字消息。' },
    actions: [{ action_id: 'request-human-assistance', intent: 'REQUEST_ASSISTANCE', input_schema_ref: 'serviceos://ui-inputs/assistance-request/v1' }], children: [],
    data_source: { kind: 'CONVERSATION_VIEW', binding: 'assistance', resource_id: ids.conversation, resource_version: 3 } })
  const health: S['HealthResponse'] = { status: 'ok', service: 'serviceos-api', version: '0.1.0' }
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path.endsWith('/events')) return route.abort()
    if (method === 'POST' && path.endsWith('/messages')) {
      const body = route.request().postDataJSON() as S['SendMessage']
      state.sent.push(body)
      const message: S['MessageRead'] = { id: crypto.randomUUID(), conversation_id: path.split('/')[4],
        author_kind: actor.kind, author_display_name: actor.kind === 'CUSTOMER' ? '客户' : '客服',
        visibility: body.visibility, content: body.content,
        client_message_id: body.client_message_id, related_case_id: null, created_at: createdAt }
      state.messages.push(message)
      return route.fulfill({ status: 202, json: { message, replayed: false, processing_state: 'QUEUED' } satisfies S['MessageReceipt'] })
    }
    if (method === 'POST' && path.endsWith('/ui-actions')) {
      const body = route.request().postDataJSON() as S['UIActionRequest']
      state.actions.push(body)
      return route.fulfill({ status: 200, json: { client_action_id: body.client_action_id, status: 'ACCEPTED',
        task_id: null, diagnostic_task_id: ids.second, replayed: false } satisfies S['UIActionResult'] })
    }
    if (method === 'POST' && /\/proposals\/[^/]+\/reply-drafts$/.test(path)) {
      const proposalId = path.split('/')[4]
      const proposal = state.proposals.find(item => item.id === proposalId)!
      const body = route.request().postDataJSON() as S['CreateReplyDraft']
      let draft = state.replyDrafts.find(item => item.id === body.draft_id)
      if (!draft) {
        draft = { id: body.draft_id, conversation_id: proposal.conversation_id, source_proposal_id: proposal.id,
          created_by: actor.actor_id, content: 'AI 建议的回复内容', status: 'IN_COMPOSER', version: 1,
          approved_by: null, sent_message_id: null, created_at: createdAt }
        state.replyDrafts.push(draft)
      }
      return route.fulfill({ status: 201, json: draft })
    }
    if (method === 'PATCH' && /\/reply-drafts\/[^/]+$/.test(path)) {
      const id = path.split('/').at(-1)!
      const draft = state.replyDrafts.find(item => item.id === id)!
      const body = route.request().postDataJSON() as S['UpdateReplyDraft']
      draft.content = body.content
      draft.version++
      draft.status = 'EDITED'
      return route.fulfill({ json: draft })
    }
    if (method === 'POST' && /\/reply-drafts\/[^/]+\/approval$/.test(path)) {
      const draft = state.replyDrafts.find(item => item.id === path.split('/')[4])!
      draft.status = 'APPROVED'
      draft.version++
      draft.approved_by = actor.actor_id
      return route.fulfill({ json: draft })
    }
    if (method === 'POST' && /\/reply-drafts\/[^/]+\/send$/.test(path)) {
      const draft = state.replyDrafts.find(item => item.id === path.split('/')[4])!
      const body = route.request().postDataJSON() as S['SendReplyDraft']
      const message: S['MessageRead'] = { id: crypto.randomUUID(), conversation_id: draft.conversation_id,
        author_kind: 'STAFF', author_display_name: '客服', visibility: 'PUBLIC',
        content: [{ type: 'text', text: draft.content }], client_message_id: body.client_message_id,
        related_case_id: null, created_at: createdAt }
      draft.status = 'SENT'
      draft.version++
      draft.sent_message_id = message.id
      state.messages.push(message)
      return route.fulfill({ status: 202, json: { message, replayed: false, processing_state: 'NOT_SCHEDULED' } satisfies S['MessageReceipt'] })
    }
    const json = method === 'GET' && path.endsWith('/auth/me') ? actor
      : method === 'GET' && path.endsWith('/health') ? health
      : method === 'GET' && path.endsWith('/conversations') ? { items: state.conversations }
      : method === 'GET' && path.endsWith('/messages') ? { items: state.messages.filter(item => path.includes(item.conversation_id)), next_cursor: null }
      : method === 'GET' && path.endsWith('/event-history') ? { items: [], next_after: 0 }
      : method === 'GET' && path.endsWith('/case-summaries') ? [summary]
      : method === 'GET' && path.endsWith('/customer-assistance') ? { items: state.assistance }
      : method === 'GET' && path.endsWith('/reply-drafts') ? state.replyDrafts
      : method === 'GET' && path === '/api/v1/tasks' ? { items: [], next_cursor: null }
      : method === 'GET' && path.endsWith('/tasks') ? []
      : method === 'GET' && path.endsWith('/proposals') ? state.proposals
      : method === 'GET' && path.endsWith('/knowledge/documents') ? { items: [], next_cursor: null }
      : method === 'GET' && path.endsWith('/guard/stats') ? { passed: 0, blocked: 0, overridden: 0 }
      : method === 'GET' && path.endsWith('/guard/decisions') ? { items: [], next_cursor: null }
      : method === 'GET' && path.endsWith('/policies') ? []
      : method === 'GET' && path.endsWith('/devices') ? [device]
      : method === 'GET' && path.endsWith(`/devices/${ids.device}`) ? device
      : method === 'GET' && path.endsWith(`/devices/${ids.device}/cases`) ? history
      : method === 'POST' && path.endsWith('/ui-document/refresh') ? document : undefined
    if (method === 'GET' && path.endsWith('/ui-document')) return route.fulfill({ json: document })
    if (json === undefined) {
      state.unexpected.push(`${method} ${path}`)
      return route.fulfill({ status: 404, json: { detail: '资源不存在或无权访问。' } })
    }
    await route.fulfill({ json })
  })
  return { ...state, actor, document }
}
