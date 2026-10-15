import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleHelp, FileText, Headphones, ListChecks, ShieldAlert, UsersRound } from 'lucide-react'
import { ApiFailure, type UIActionBody, type UIDocument, invokeUIAction } from '../../api/client'
import { StatusBadge } from '../../shared/StatusBadge'
import { clearPendingAction, readPendingAction, savePendingAction } from './actionRecovery'

const catalog: Record<string, readonly string[]> = {
  CaseSummaryCard: ['title', 'body', 'status', 'source', 'verification'],
  EvidenceSummary: ['title', 'body', 'source', 'verification'],
  QuestionForm: ['title', 'body'], RiskAlert: ['title', 'body'],
  ProgressTimeline: ['title', 'body', 'status'], HandoffSummary: ['title', 'body', 'status'],
  ActionBar: ['title', 'body'],
}
const uuid = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i
const isRecord = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const isText = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0 && value.length <= 2000
const positiveInteger = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0

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
      !positiveInteger(source.resource_version) || !['CONVERSATION_VIEW', 'CASE_VIEW', 'TASK_VIEW', 'AGENT_RUN_VIEW'].includes(String(source.kind)) ||
      (source.kind === 'CONVERSATION_VIEW' && (source.resource_id !== conversationId || source.resource_version !== version)) ||
      (!desk && !['CONVERSATION_VIEW', 'AGENT_RUN_VIEW'].includes(String(source.kind)))) return false
    if (!Array.isArray(item.actions) || item.actions.length > 1 ||
      !Array.isArray(item.children) || item.children.length > 4 || item.children.some(child => typeof child !== 'string')) return false
    if (item.type === 'ActionBar') {
      const action = item.actions[0]
      if (desk || item.actions.length !== 1 || !isRecord(action) ||
        action.intent !== 'REQUEST_ASSISTANCE' || action.action_id !== 'request-human-assistance' ||
        action.input_schema_ref !== 'serviceos://ui-inputs/assistance-request/v1' ||
        Object.keys(action).length !== 3 || source.kind !== 'CONVERSATION_VIEW') return false
    } else if (item.actions.length) return false
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

export function UIDocumentRenderer({ document, conversationId, conversationVersion, active, desk, recoveryKey, loading = false, onReply, onCompleted, onRefresh }: {
  document: UIDocument | null
  conversationId: string
  conversationVersion: number
  active: boolean
  desk: boolean
  recoveryKey: string
  loading?: boolean
  onReply?: () => void
  onCompleted: () => void
  onRefresh: () => void
}) {
  const [reason, setReason] = useState('需要真人协助处理当前问题')
  const [pending, setPending] = useState<UIActionBody | null>(() => readPendingAction(recoveryKey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')
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
  const supported = audienceMatches && revisionValid && !regressed &&
    document.schema_version === 1 && document.catalog_version === 1 && document.status === 'ACTIVE' &&
    (desk ? document.surface === 'DESK_PANEL' : ['SUPPORT_INLINE', 'SUPPORT_PANEL'].includes(document.surface)) &&
    (expires === null || expires > Date.now()) && validComponents(document.components, conversationId, conversationVersion, desk)

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
  const feedback = <>{recovery}{result && <p role="status">{result}</p>}{error && <p className="form-error" role="alert">{error}</p>}</>

  if (!supported || !document) return <section className="ui-document" aria-label={desk ? '客服交互卡' : '服务交互卡'}>
    <p className="ui-fallback">{loading ? '正在加载交互卡…' : audienceMatches && isText(document?.fallback_text) ? document.fallback_text : '暂无可用交互卡；可继续使用文字消息。'}</p>
    {!loading && document && <div className="ui-fallback-actions"><p>卡片不可用、版本已变化或内容不受支持，未启用新操作。</p><button type="button" onClick={onRefresh}>刷新交互卡</button></div>}
    {feedback}
  </section>

  // Safety notices precede questions; assistance stays secondary. Render each ID once,
  // even if a valid document also references it as a child.
  const components = [...document.components].sort((a, b) =>
    (a.type === 'RiskAlert' ? -1 : a.type === 'ActionBar' ? 1 : 0) - (b.type === 'RiskAlert' ? -1 : b.type === 'ActionBar' ? 1 : 0))
  return <section className="ui-document" aria-label={desk ? '客服交互卡' : '服务交互卡'}>
    <p className="ui-version">交互卡修订 {document.revision}</p>
    {components.map((component) => {
      const Icon = component.type === 'RiskAlert' ? ShieldAlert : component.type === 'QuestionForm' ? CircleHelp :
        component.type === 'ActionBar' ? Headphones : component.type === 'HandoffSummary' ? UsersRound :
          component.type === 'ProgressTimeline' ? ListChecks : FileText
      return <article className={`ui-card ui-${component.type}`} key={component.id}>
        <h3><Icon size={18} aria-hidden="true" />{component.props.title}</h3>
        {component.type === 'ProgressTimeline' ? <ol className="ui-timeline"><li><p>{component.props.body}</p><StatusBadge value={component.props.status} label={component.props.status === 'FAILED' ? '处理失败' : undefined} /></li></ol> : <p>{component.props.body}</p>}
        {(component.type === 'CaseSummaryCard' || component.type === 'HandoffSummary') && <p><StatusBadge value={component.props.status} label={component.props.status === 'FAILED' ? '处理失败' : undefined} /></p>}
        {'source' in component.props && <dl className="ui-evidence-meta"><div><dt>来源</dt><dd>{component.props.source}</dd></div>
          <div><dt>核验</dt><dd><StatusBadge value={component.props.verification} /></dd></div></dl>}
        {component.type === 'QuestionForm' && !desk && <div className="ui-question-reply"><small>直接用文字回答；不便操作也可以说明。</small>{onReply && <button type="button" disabled={!active} onClick={onReply}>填写回复</button>}</div>}
        {desk && component.data_source.kind === 'CASE_VIEW' && <Link className="ui-case-link" to={`/cases/${component.data_source.resource_id}`}>查看案例与证据</Link>}
        {component.type === 'ActionBar' && !result && !pending && <div className="ui-action">
          <label htmlFor={`assistance-reason-${document.ui_id}`}>请求原因</label>
          <input id={`assistance-reason-${document.ui_id}`} value={reason} maxLength={1000} disabled={busy || !active}
            onChange={(event) => setReason(event.target.value)} />
          <button type="button" disabled={busy || !active || reason.trim().length < 3} onClick={requestHuman}>{busy ? '正在保存…' : '请求人工协助'}</button>
          {!active && <small>此会话已归档，不能提交新请求。</small>}
        </div>}
      </article>
    })}
    {feedback}
  </section>
}
