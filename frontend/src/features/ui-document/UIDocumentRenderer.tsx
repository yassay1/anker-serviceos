import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, CircleHelp, FileText, Headphones, ListChecks, ShieldAlert, UsersRound } from 'lucide-react'
import { ApiFailure, type UIActionBody, type UIDocument, invokeUIAction } from '../../api/client'
import { StatusBadge } from '../../shared/StatusBadge'
import { clearPendingAction, readPendingAction, savePendingAction } from './actionRecovery'

const catalog: Record<string, readonly string[]> = {
  CaseSummaryCard: ['title', 'body', 'status', 'source', 'verification'],
  EvidenceSummary: ['title', 'body', 'source', 'verification'],
  QuestionForm: ['title', 'body'], RiskAlert: ['title', 'body'],
  // ChoiceGroup carries its choices in the component-level options field: prop values are
  // always strings, so a choice list can never travel inside props.
  ChoiceGroup: ['title', 'body'],
  ProgressTimeline: ['title', 'body', 'status'], HandoffSummary: ['title', 'body', 'status'],
  ActionBar: ['title', 'body'],
  KnowledgeMetricChart: ['title', 'body'], CaseProcessFlow: ['title', 'body'],
}
const optionTypes = new Set(['ChoiceGroup'])
const optionSlug = /^[a-z0-9-]{1,32}$/

/** Choices are inert: a label to send and a stable slug. Only the collecting types may carry them. */
function validOptions(value: unknown, type: string): boolean {
  if (value === undefined) return type !== 'ChoiceGroup'
  if (!Array.isArray(value) || value.length > 5) return false
  if (type === 'ChoiceGroup' && value.length < 2) return false
  if (value.length && !optionTypes.has(type)) return false
  const labels = new Set<string>()
  const slugs = new Set<string>()
  return value.every(option => {
    if (!isRecord(option) || Object.keys(option).length !== 2) return false
    const { label, value: slug } = option
    if (typeof label !== 'string' || !label.trim() || label.length > 40 || /<|>|https?:\/\/|javascript:|data:|\bon\w+\s*=/i.test(label)) return false
    if (typeof slug !== 'string' || !optionSlug.test(slug) || labels.has(label.trim()) || slugs.has(slug)) return false
    labels.add(label.trim())
    slugs.add(slug)
    return true
  })
}
const uuid = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i
const isRecord = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0 && value.length <= 2000
const positiveInteger = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0
const chartPoints = [{ label: '5 分钟', value: 10 }, { label: '10 分钟', value: 20 }, { label: '15 分钟', value: 30 }]
const flowIds = new Set(['case', 'human-task', 'service-action', 'verification'])
const flowStatuses = new Set(['NOT_STARTED', 'IN_PROGRESS', 'WAITING', 'COMPLETED', 'FAILED', 'UNKNOWN', 'NOT_APPLICABLE'])
const flowStatusLabels: Record<string, string> = {
  NOT_STARTED: '未开始', IN_PROGRESS: '处理中', WAITING: '等待中', COMPLETED: '已完成',
  FAILED: '未通过', UNKNOWN: '未知', NOT_APPLICABLE: '不适用',
}

type ChartData = { metric_id: string, chart_type: string, x_axis_label: string, y_axis_label: string, unit: string,
  points: { label: string, value: number }[], source_label: string, source_version: string, note: string }
type FlowNode = { id: string, label: string, status: string, detail: string, resource_kind: string,
  resource_id: string, resource_version: number }
type FlowData = { nodes: FlowNode[], edges: { source: string, target: string }[] }
type VisualComponent = UIDocument['components'][number] & { chart?: unknown, flow?: unknown }

function safeVisualText(value: unknown, limit: number): value is string {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= limit &&
    !/<|>|https?:\/\/|javascript:|data:|\bon\w+\s*=/i.test(value)
}

function validChart(value: unknown): value is ChartData {
  if (!isRecord(value) || Object.keys(value).length !== 9) return false
  return value.metric_id === 'heating-extra-battery' && value.chart_type === 'BAR' &&
    value.x_axis_label === '加热时长（分钟）' && value.y_axis_label === '额外电量消耗' && value.unit === '%' &&
    Array.isArray(value.points) && JSON.stringify(value.points) === JSON.stringify(chartPoints) &&
    safeVisualText(value.source_label, 180) && typeof value.source_version === 'string' && /^[\da-f]{16}$/.test(value.source_version) &&
    safeVisualText(value.note, 240)
}

function validFlow(value: unknown, source: Record<string, unknown>): value is FlowData {
  if (!isRecord(value) || Object.keys(value).length !== 2 || !Array.isArray(value.nodes) ||
    value.nodes.length < 1 || value.nodes.length > 8 || !Array.isArray(value.edges) || value.edges.length > 8) return false
  const nodes = value.nodes as unknown[]
  const ids = new Set<string>()
  for (const raw of nodes) {
    if (!isRecord(raw) || Object.keys(raw).length !== 7 || typeof raw.id !== 'string' || !flowIds.has(raw.id) || ids.has(raw.id) ||
      !safeVisualText(raw.label, 80) || typeof raw.status !== 'string' || !flowStatuses.has(raw.status) ||
      !safeVisualText(raw.detail, 240) || !['CASE_VIEW', 'TASK_VIEW'].includes(String(raw.resource_kind)) ||
      typeof raw.resource_id !== 'string' || !uuid.test(raw.resource_id) || !positiveInteger(raw.resource_version)) return false
    if (raw.id === 'human-task') {
      if (raw.resource_kind !== 'TASK_VIEW') return false
    } else if (raw.resource_kind !== 'CASE_VIEW' || raw.resource_id !== source.resource_id ||
      raw.resource_version !== source.resource_version) return false
    ids.add(raw.id)
  }
  if (!ids.has('case')) return false
  const adjacency = new Map([...ids].map(id => [id, [] as string[]]))
  const pairs = new Set<string>()
  for (const raw of value.edges as unknown[]) {
    if (!isRecord(raw) || Object.keys(raw).length !== 2 || typeof raw.source !== 'string' || typeof raw.target !== 'string' ||
      !ids.has(raw.source) || !ids.has(raw.target) || raw.source === raw.target) return false
    const key = `${raw.source}:${raw.target}`
    if (pairs.has(key)) return false
    pairs.add(key)
    adjacency.get(raw.source)?.push(raw.target)
  }
  const visiting = new Set<string>(), visited = new Set<string>()
  const visit = (id: string): boolean => {
    if (visiting.has(id)) return false
    if (visited.has(id)) return true
    visiting.add(id)
    for (const target of adjacency.get(id) ?? []) if (!visit(target)) return false
    visiting.delete(id); visited.add(id)
    return true
  }
  return [...ids].every(visit)
}

function validComponents(value: unknown, conversationId: string, version: number, desk: boolean): value is UIDocument['components'] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 12) return false
  const ids = new Set<string>()
  for (const item of value) {
    if (!isRecord(item) || typeof item.id !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(item.id) || ids.has(item.id) ||
      typeof item.type !== 'string' || !Object.hasOwn(catalog, item.type) || !isRecord(item.props)) return false
    ids.add(item.id)
    const fields = catalog[item.type]
    const props = item.props
    if (Object.keys(props).length !== fields.length || fields.some(field => !isText(props[field]))) return false
    const source = item.data_source
    if (!isRecord(source) || typeof source.resource_id !== 'string' || !uuid.test(source.resource_id) ||
      !positiveInteger(source.resource_version) || !['CONVERSATION_VIEW', 'CASE_VIEW', 'TASK_VIEW', 'AGENT_RUN_VIEW', 'DIAGNOSTIC_TASK_VIEW'].includes(String(source.kind)) ||
      (source.kind === 'CONVERSATION_VIEW' && (source.resource_id !== conversationId || source.resource_version !== version)) ||
      (!desk && !['CONVERSATION_VIEW', 'AGENT_RUN_VIEW', 'DIAGNOSTIC_TASK_VIEW'].includes(String(source.kind)) &&
        !(source.kind === 'CASE_VIEW' && source.binding === 'progress' && item.type === 'ProgressTimeline'))) return false
    if (source.kind === 'DIAGNOSTIC_TASK_VIEW') {
      if (desk || item.type !== 'QuestionForm' && item.type !== 'ChoiceGroup' || source.binding !== 'question' ||
        !positiveInteger(source.question_revision) || !Array.isArray(item.actions) || item.actions.length !== 1) return false
    } else if (source.question_revision !== undefined && source.question_revision !== null) return false
    if (!Array.isArray(item.actions) || item.actions.length > 1 ||
      !Array.isArray(item.children) || item.children.length > 4 || item.children.some(child => typeof child !== 'string')) return false
    if (item.type === 'ActionBar') {
      const action = item.actions[0]
      if (desk || item.actions.length !== 1 || !isRecord(action) ||
        action.intent !== 'REQUEST_ASSISTANCE' || action.action_id !== 'request-human-assistance' ||
        action.input_schema_ref !== 'serviceos://ui-inputs/assistance-request/v1' ||
        Object.keys(action).length !== 3 || source.kind !== 'CONVERSATION_VIEW') return false
    } else if (source.kind === 'DIAGNOSTIC_TASK_VIEW') {
      const action = item.actions[0]
      if (!isRecord(action) || action.intent !== 'SUBMIT_DIAGNOSTIC_ANSWER' ||
        action.action_id !== 'submit-diagnostic-answer' || action.input_schema_ref !== 'serviceos://ui-inputs/diagnostic-answer/v1' ||
        Object.keys(action).length !== 3) return false
    } else if (item.actions.length) return false
    const options = (item as { options?: unknown }).options ?? []
    if (!validOptions(options, item.type)) return false
    const visual = item as VisualComponent
    if (item.type === 'KnowledgeMetricChart') {
      if (desk || !validChart(visual.chart) || visual.flow != null || source.kind !== 'AGENT_RUN_VIEW' || source.binding !== 'metric' || item.actions.length) return false
    } else if (visual.chart != null) return false
    if (item.type === 'CaseProcessFlow') {
      if (!desk || !validFlow(visual.flow, source) || visual.chart != null || source.kind !== 'CASE_VIEW' || source.binding !== 'process_flow' || item.actions.length) return false
    } else if (visual.flow != null) return false
  }
  const components = value as UIDocument['components']
  const byId = new Map(components.map(component => [component.id, component]))
  const visit = (id: string, path: string[]): boolean => {
    const item = byId.get(id)
    return Boolean(item && path.length <= 2 && !path.includes(id) && item.children.every(child => visit(child, [...path, id])))
  }
  return components.every(component => visit(component.id, []))
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : '交互卡暂不可用，请使用文字消息。'
}

export function UIDocumentRenderer({ document, conversationId, conversationVersion, active, desk, recoveryKey, loading = false, placement = 'inline', onReply, onChoose, onCompleted, onRefresh }: {
  document: UIDocument | null
  conversationId: string
  conversationVersion: number
  active: boolean
  desk: boolean
  recoveryKey: string
  loading?: boolean
  placement?: 'inline' | 'assistance'
  onReply?: () => void
  onChoose?: (label: string) => Promise<boolean>
  onCompleted: () => void
  onRefresh: () => void
}) {
  const [reason, setReason] = useState('需要真人协助处理当前问题')
  const [pending, setPending] = useState<UIActionBody | null>(() => readPendingAction(recoveryKey))
  const diagnosticRecoveryKey = `${recoveryKey}:diagnostic`
  const [diagnosticPending, setDiagnosticPending] = useState<UIActionBody | null>(() => readPendingAction(diagnosticRecoveryKey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')
  // Choice feedback is kept apart from the assistance result: sending a choice must not
  // hide the assistance action, which stays available for the rest of the conversation.
  const [choiceSubmission, setChoiceSubmission] = useState<{ uiId: string, revision: number, status: string } | null>(null)
  const [diagnosticSubmission, setDiagnosticSubmission] = useState<{ uiId: string, revision: number, status: string } | null>(null)
  const [answerDraft, setAnswerDraft] = useState('')
  const [assistanceOpen, setAssistanceOpen] = useState(false)
  const [, tick] = useState(0)
  const latest = useRef<{ uiId: string, revision: number } | null>(null)
  const audienceMatches = isRecord(document) && document.audience === (desk ? 'STAFF' : 'CUSTOMER') &&
    document.visibility === (desk ? 'INTERNAL' : 'PUBLIC')
  const revisionValid = audienceMatches && typeof document.ui_id === 'string' && uuid.test(document.ui_id) && positiveInteger(document.revision)
  const regressed = revisionValid && latest.current?.uiId === document.ui_id && document.revision < latest.current.revision
  if (revisionValid && !regressed) latest.current = { uiId: document.ui_id, revision: document.revision }
  const expires = document?.expires_at ? Date.parse(document.expires_at) : null
  useEffect(() => {
    if (expires === null || !Number.isFinite(expires) || expires <= Date.now()) return
    const timer = window.setTimeout(() => tick(value => value + 1), Math.min(expires - Date.now() + 1, 2_147_483_647))
    return () => window.clearTimeout(timer)
  }, [expires])
  // Catalog 2 added ChoiceGroup; catalog 4 adds the customer-safe linked Case progress binding.
  // Older documents remain renderable with their original source restrictions.
  const supported = audienceMatches && revisionValid && !regressed &&
    document.schema_version === 1 && [1, 2, 3, 4].includes(document.catalog_version) && document.status === 'ACTIVE' &&
    (desk ? document.surface === 'DESK_PANEL' : ['SUPPORT_INLINE', 'SUPPORT_PANEL'].includes(document.surface)) &&
    (expires === null || expires > Date.now()) && validComponents(document.components, conversationId, conversationVersion, desk)
  const choiceSubmitted = Boolean(document && choiceSubmission?.uiId === document.ui_id && choiceSubmission.revision === document.revision)
  const diagnosticSubmitted = Boolean(document && diagnosticSubmission?.uiId === document.ui_id &&
    diagnosticSubmission.revision === document.revision && diagnosticSubmission.status.startsWith('回答已保存'))

  function updatePending(body: UIActionBody) {
    savePendingAction(recoveryKey, body)
    setPending(body)
  }
  function clearCompletedRequest(body: UIActionBody) {
    clearPendingAction(recoveryKey, body.client_action_id)
    setPending(current => current?.client_action_id === body.client_action_id ? null : current)
  }
  async function submit(body: UIActionBody) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const response = await invokeUIAction(conversationId, body)
      clearCompletedRequest(body)
      setResult(response.replayed ? '人工协助请求已存在。' : '人工协助请求已保存。')
      onCompleted()
    } catch (failure) {
      setError(errorText(failure))
      // Only a definitive refusal releases the idempotency key. Never automatically
      // replay a write when a new revision or a reconnected snapshot arrives.
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) clearCompletedRequest(body)
      onRefresh()
    } finally {
      setBusy(false)
    }
  }
  async function choose(label: string) {
    // The workspace queues this as an ordinary customer message and retains its idempotency key
    // for a retry when the transport result is unknown.
    if (busy || choiceSubmitted || !onChoose || !active || !supported || !document || (expires !== null && expires <= Date.now())) return
    setBusy(true)
    setError('')
    setChoiceSubmission({ uiId: document.ui_id, revision: document.revision, status: '正在发送选项…' })
    try {
      const saved = await onChoose(label)
      setChoiceSubmission({ uiId: document.ui_id, revision: document.revision,
        status: saved ? `已发送：${label}` : '发送结果未确认，请在消息列表中用原消息重试。' })
      if (saved) onCompleted()
    } catch (failure) {
      setError(errorText(failure))
      setChoiceSubmission({ uiId: document.ui_id, revision: document.revision,
        status: '发送结果未确认，请在消息列表中用原消息重试。' })
    } finally {
      setBusy(false)
    }
  }
  async function submitDiagnosticAnswer(component: UIDocument['components'][number], answer: string) {
    if (busy || diagnosticPending || !active || !supported || !document ||
      component.data_source.kind !== 'DIAGNOSTIC_TASK_VIEW' || !component.data_source.question_revision ||
      !answer.trim() || answer.length > 1000) return
    const body: UIActionBody = {
      client_action_id: crypto.randomUUID(), ui_id: document.ui_id, revision: document.revision,
      action_id: 'submit-diagnostic-answer',
      input: { task_version: component.data_source.resource_version,
        question_revision: component.data_source.question_revision, answer: answer.trim() },
      expected_conversation_version: conversationVersion,
    }
    savePendingAction(diagnosticRecoveryKey, body)
    setDiagnosticPending(body)
    setBusy(true)
    setError('')
    setDiagnosticSubmission({ uiId: document.ui_id, revision: document.revision, status: '正在提交回答…' })
    try {
      await invokeUIAction(conversationId, body)
      clearPendingAction(diagnosticRecoveryKey, body.client_action_id)
      setDiagnosticPending(null)
      setDiagnosticSubmission({ uiId: document.ui_id, revision: document.revision, status: '回答已保存，诊断专家将继续分析。' })
      setAnswerDraft('')
      onCompleted()
    } catch (failure) {
      setError(errorText(failure))
      setDiagnosticSubmission({ uiId: document.ui_id, revision: document.revision, status: '回答状态尚未确认。' })
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        clearPendingAction(diagnosticRecoveryKey, body.client_action_id)
        setDiagnosticPending(null)
      }
      onRefresh()
    } finally {
      setBusy(false)
    }
  }
  async function retryDiagnosticAnswer() {
    if (!diagnosticPending || busy) return
    setBusy(true)
    setError('')
    try {
      await invokeUIAction(conversationId, diagnosticPending)
      clearPendingAction(diagnosticRecoveryKey, diagnosticPending.client_action_id)
      setDiagnosticPending(null)
      setDiagnosticSubmission({ uiId: diagnosticPending.ui_id, revision: diagnosticPending.revision,
        status: '回答已保存，诊断专家将继续分析。' })
      onCompleted()
    } catch (failure) {
      setError(errorText(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        clearPendingAction(diagnosticRecoveryKey, diagnosticPending.client_action_id)
        setDiagnosticPending(null)
      }
      onRefresh()
    } finally {
      setBusy(false)
    }
  }
  function requestHuman() {
    if (busy || !active || !supported || !document || (expires !== null && expires <= Date.now()) || reason.trim().length < 3 || reason.length > 1000) return
    const body: UIActionBody = pending ?? {
      client_action_id: crypto.randomUUID(), ui_id: document.ui_id,
      revision: document.revision, action_id: 'request-human-assistance',
      input: { reason: reason.trim() }, expected_conversation_version: conversationVersion,
    }
    updatePending(body)
    void submit(body)
  }
  const recovery = pending && <div className="ui-action ui-recovery">
    <p>上次操作结果未确认，请先查询原请求结果。</p>
    <label htmlFor="pending-assistance-reason">请求原因</label>
    <input id="pending-assistance-reason" value={String(pending.input.reason)} disabled />
    <button type="button" disabled={busy} onClick={() => void submit(pending)}>{busy ? '正在查询…' : '用原请求重试'}</button>
  </div>
  const diagnosticRecovery = diagnosticPending && <div className="ui-action ui-recovery">
    <p>上次诊断回答结果未确认，请先查询原请求结果。</p>
    <label htmlFor="pending-diagnostic-answer">原回答</label>
    <input id="pending-diagnostic-answer" value={String(diagnosticPending.input.answer ?? '')} disabled />
    <button type="button" disabled={busy} onClick={() => void retryDiagnosticAnswer()}>{busy ? '正在查询…' : '用原回答重试'}</button>
  </div>
  const feedback = <>{placement === 'assistance' && recovery}{placement === 'inline' && <>{diagnosticRecovery}{choiceSubmitted && <p role="status">{choiceSubmission?.status}</p>}{diagnosticSubmission && document && diagnosticSubmission.uiId === document.ui_id && <p role="status">{diagnosticSubmission.status}</p>}</>}{result && placement === 'assistance' && <p role="status">{result}</p>}{error && <p className="form-error" role="alert">{error}</p>}</>

  if (!desk && placement === 'assistance' && (!supported || !document)) return null
  if (!supported || !document) return <section className="ui-document" aria-label={desk ? '客服交互卡' : '服务交互卡'}>
    <p className="ui-fallback">{loading ? '正在加载交互卡…' : audienceMatches && isText(document?.fallback_text) ? document.fallback_text : '暂无可用交互卡；可继续使用文字消息。'}</p>
    {!loading && document && <div className="ui-fallback-actions"><p>卡片不可用、版本已变化或内容不受支持，未启用新操作。</p><button type="button" onClick={onRefresh}>刷新交互卡</button></div>}
    {placement === 'inline' && feedback}
  </section>

  // Safety notices precede questions; assistance stays secondary. Render each ID once,
  // even if a valid document also references it as a child.
  const components = [...document.components].sort((a, b) =>
    (a.type === 'RiskAlert' ? -1 : a.type === 'ActionBar' ? 1 : 0) - (b.type === 'RiskAlert' ? -1 : b.type === 'ActionBar' ? 1 : 0))
  const visibleComponents = components.filter(component => desk || (placement === 'assistance' ? component.type === 'ActionBar' : component.type !== 'ActionBar'))
  if (!desk && placement === 'assistance' && !visibleComponents.length) return null
  return <section className="ui-document" aria-label={desk ? '客服交互卡' : '服务交互卡'}>
    {desk && <p className="ui-version">交互卡修订 {document.revision}</p>}
    {visibleComponents.map((component) => {
      const Icon = component.type === 'RiskAlert' ? ShieldAlert : (component.type === 'QuestionForm' || component.type === 'ChoiceGroup') ? CircleHelp :
        component.type === 'ActionBar' ? Headphones : component.type === 'HandoffSummary' ? UsersRound :
          component.type === 'ProgressTimeline' ? ListChecks : FileText
      const Card = component.type === 'ActionBar' && placement === 'inline' ? 'details' : 'article'
      const Heading = component.type === 'ActionBar' && placement === 'inline' ? 'summary' : 'h3'
      return <Card className={`ui-card ui-${component.type}`} key={component.id}>
        {!(component.type === 'ActionBar' && placement === 'assistance') &&
          <Heading><Icon size={18} aria-hidden="true" />{component.props.title}{component.type === 'ActionBar' && <span className="assistance-expand">展开申请</span>}</Heading>}
        {component.type === 'ProgressTimeline' ? <div className="ui-progress-summary" role="status" aria-label={`当前服务进度：${component.props.status}`}>
          <span className={`ui-progress-rail status-${component.props.status}`} aria-hidden="true"><span /></span>
          <div className="ui-progress-copy"><p>{component.props.body}</p><StatusBadge value={component.props.status} label={component.props.status === 'FAILED' ? '处理失败' : undefined} /></div>
        </div> :
          !(component.type === 'ActionBar' && placement === 'assistance') && <p>{component.props.body}</p>}
        {component.type === 'KnowledgeMetricChart' && (() => {
          const chart = (component as VisualComponent).chart as ChartData
          return <div className="ui-chart-wrap">
            <svg className="ui-chart" viewBox="0 0 360 210" role="img" aria-label={`${chart.y_axis_label}柱状图`}>
              <text x="12" y="18" className="ui-chart-axis-label">{chart.y_axis_label}（{chart.unit}）</text>
              <line x1="42" y1="162" x2="344" y2="162" className="ui-chart-axis" />
              {chart.points.map((point, index) => {
                const height = point.value * 3
                const x = 68 + index * 92
                return <g key={point.label}>
                  <rect x={x} y={162 - height} width="42" height={height} rx="4" className="ui-chart-bar" />
                  <text x={x + 21} y={151 - height} textAnchor="middle" className="ui-chart-value">{point.value}{chart.unit}</text>
                  <text x={x + 21} y="181" textAnchor="middle" className="ui-chart-tick">{point.label}</text>
                </g>
              })}
              <text x="190" y="204" textAnchor="middle" className="ui-chart-axis-label">{chart.x_axis_label}</text>
            </svg>
            <dl className="ui-chart-source"><div><dt>来源</dt><dd>{chart.source_label}</dd></div>
              <div><dt>来源版本</dt><dd>{chart.source_version}</dd></div></dl>
            <p className="ui-visual-note">{chart.note}</p>
          </div>
        })()}
        {component.type === 'CaseProcessFlow' && (() => {
          const flow = (component as VisualComponent).flow as FlowData
          const layout: Record<string, { x: number, y: number }> = {
            case: { x: 72, y: 66 }, 'human-task': { x: 220, y: 32 },
            'service-action': { x: 220, y: 100 }, verification: { x: 368, y: 66 },
          }
          const positions = new Map(flow.nodes.map(node => [node.id, layout[node.id]]))
          return <div className="ui-flow-wrap">
            <svg className="ui-flow" viewBox="0 0 440 150" role="img" aria-label="案例办理流程图">
              {flow.edges.map(edge => {
                const from = positions.get(edge.source), to = positions.get(edge.target)
                if (!from || !to) return null
                return <line key={`${edge.source}-${edge.target}`} x1={from.x + 55} y1={from.y} x2={to.x - 55} y2={to.y} className="ui-flow-edge" />
              })}
              {flow.nodes.map(node => {
                const point = positions.get(node.id)!
                return <g key={node.id}>
                  <rect x={point.x - 58} y={point.y - 28} width="116" height="56" rx="9" className={`ui-flow-node status-${node.status}`} />
                  <text x={point.x} y={point.y - 3} textAnchor="middle" className="ui-flow-label">{node.label}</text>
                  <text x={point.x} y={point.y + 15} textAnchor="middle" className="ui-flow-status">{flowStatusLabels[node.status]}</text>
                </g>
              })}
            </svg>
            <ol className="ui-flow-details">{flow.nodes.map(node => <li key={node.id}>
              <strong>{node.label} · {flowStatusLabels[node.status]}</strong><span>{node.detail}</span>
            </li>)}</ol>
          </div>
        })()}
        {(component.type === 'CaseSummaryCard' || component.type === 'HandoffSummary') && <p><StatusBadge value={component.props.status} label={component.props.status === 'FAILED' ? '处理失败' : undefined} /></p>}
        {'source' in component.props && <dl className="ui-evidence-meta"><div><dt>来源</dt><dd>{component.props.source}</dd></div>
          <div><dt>核验</dt><dd><StatusBadge value={component.props.verification} /></dd></div></dl>}
        {component.type === 'QuestionForm' && !desk && component.data_source.kind === 'DIAGNOSTIC_TASK_VIEW' && <form className="ui-question-reply" onSubmit={(event) => {
          event.preventDefault(); void submitDiagnosticAnswer(component, answerDraft)
        }}>
          <label htmlFor="diagnostic-answer">你的回答</label>
          <textarea id="diagnostic-answer" value={answerDraft} maxLength={1000} disabled={busy || diagnosticSubmitted || Boolean(diagnosticPending) || !active}
            onChange={(event) => setAnswerDraft(event.target.value)} />
          <button type="submit" disabled={busy || diagnosticSubmitted || Boolean(diagnosticPending) || !active || !answerDraft.trim()}>{busy ? '正在提交…' : '提交给诊断专家'}</button>
        </form>}
        {component.type === 'QuestionForm' && !desk && component.data_source.kind !== 'DIAGNOSTIC_TASK_VIEW' && <div className="ui-question-reply"><small>直接用文字回答；不便操作也可以说明。</small>{onReply && <button type="button" disabled={!active} onClick={onReply}>填写回复</button>}</div>}
        {component.type === 'ChoiceGroup' && !desk && <div className="ui-choices">
          <small>{component.data_source.kind === 'DIAGNOSTIC_TASK_VIEW' ? '选择一项回答诊断专家。' : '选一个最接近的情况，也可以直接用文字回答。'}</small>
          <div role="group" aria-label={component.props.title}>
            {(component.options ?? []).map(option => <button type="button" key={option.value}
              disabled={busy || (component.data_source.kind === 'DIAGNOSTIC_TASK_VIEW' ? diagnosticSubmitted || Boolean(diagnosticPending) : choiceSubmitted || !onChoose) || !active}
              onClick={() => component.data_source.kind === 'DIAGNOSTIC_TASK_VIEW'
                ? void submitDiagnosticAnswer(component, option.label) : void choose(option.label)}><span>{option.label}</span><ChevronRight size={17} aria-hidden="true" /></button>)}
          </div>
        </div>}
        {desk && component.data_source.kind === 'CASE_VIEW' && <Link className="ui-case-link" to={`/cases/${component.data_source.resource_id}`}>查看案例与证据</Link>}
        {component.type === 'ActionBar' && placement === 'assistance' && !result && !pending && <div className="ui-action">
          {!assistanceOpen ? <button type="button" disabled={!active} onClick={() => setAssistanceOpen(true)}>请求真人协助</button> : <>
            <label htmlFor={`assistance-reason-${document.ui_id}`}>补充说明</label>
            <input id={`assistance-reason-${document.ui_id}`} value={reason} maxLength={1000} disabled={busy || !active}
              onChange={(event) => setReason(event.target.value)} />
            <button type="button" disabled={busy || !active || reason.trim().length < 3} onClick={requestHuman}>{busy ? '正在提交…' : '提交协助请求'}</button>
            <button type="button" className="text-button" disabled={busy} onClick={() => setAssistanceOpen(false)}>取消</button>
          </>}
          {!active && <small>此会话已归档，不能提交新请求。</small>}
        </div>}
      </Card>
    })}
    {feedback}
  </section>
}
