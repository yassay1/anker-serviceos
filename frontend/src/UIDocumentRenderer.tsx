import { useState } from 'react'
import { type UIActionBody, type UIDocument, invokeUIAction } from './api/client'

const catalog = new Set([
  'CaseSummaryCard', 'EvidenceSummary', 'QuestionForm', 'RiskAlert',
  'ProgressTimeline', 'HandoffSummary', 'ActionBar',
])

function errorText(error: unknown) {
  return error instanceof Error ? error.message : '交互卡暂不可用，请使用文字消息。'
}

export function UIDocumentRenderer({ document, conversationId, conversationVersion, desk, onCompleted, onRefresh }: {
  document: UIDocument | null
  conversationId: string
  conversationVersion: number
  desk: boolean
  onCompleted: () => void
  onRefresh: () => void
}) {
  const [reason, setReason] = useState('需要真人协助处理当前问题')
  const [pending, setPending] = useState<UIActionBody | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')

  if (!document) return <p className="ui-fallback">暂无交互卡；可继续使用文字消息。</p>
  const supported = document.schema_version === 1 && document.catalog_version === 1 &&
    document.status === 'ACTIVE' && document.audience === (desk ? 'STAFF' : 'CUSTOMER') &&
    document.visibility === (desk ? 'INTERNAL' : 'PUBLIC') &&
    (!document.expires_at || new Date(document.expires_at).getTime() > Date.now()) &&
    document.components.length <= 12 && document.components.every((component) =>
      catalog.has(component.type) && typeof component.props.title === 'string' &&
      typeof component.props.body === 'string')
  if (!supported) return <p className="ui-fallback" role="status">{document.fallback_text || '交互卡暂不可用，请使用文字消息。'}</p>

  async function submit(body: UIActionBody) {
    setBusy(true)
    setError('')
    try {
      const response = await invokeUIAction(conversationId, body)
      setPending(null)
      setResult(response.replayed ? '人工协助请求已存在。' : '人工协助请求已保存。')
      onCompleted()
    } catch (failure) {
      setError(errorText(failure))
      onRefresh()
    } finally {
      setBusy(false)
    }
  }

  function requestHuman() {
    if (reason.trim().length < 3 || reason.length > 1000) return
    const body: UIActionBody = pending ?? {
      client_action_id: crypto.randomUUID(), ui_id: document!.ui_id,
      revision: document!.revision, action_id: 'request-human-assistance',
      input: { reason: reason.trim() }, expected_conversation_version: conversationVersion,
    }
    setPending(body)
    void submit(body)
  }

  return <section className="ui-document" aria-label={desk ? '客服交互卡' : '服务交互卡'}>
    <p className="ui-version">交互卡修订 {document.revision}</p>
    {document.components.map((component) => <article className="ui-card" key={component.id}>
      <h3>{component.props.title}</h3>
      <p>{component.props.body}</p>
      {'status' in component.props && <small>状态：{component.props.status}</small>}
      {'source' in component.props && <small>来源：{component.props.source}</small>}
      {'verification' in component.props && <small>核验：{component.props.verification === 'VERIFIED' ? '已核验' : '待核验'}</small>}
      {component.type === 'ActionBar' && !desk && component.actions.some((action) => action.intent === 'REQUEST_ASSISTANCE') && <div className="ui-action">
        <label htmlFor={`assistance-reason-${document.ui_id}`}>请求原因</label>
        <input id={`assistance-reason-${document.ui_id}`} value={reason} maxLength={1000}
          onChange={(event) => { setReason(event.target.value); setPending(null) }} />
        <button type="button" disabled={busy || reason.trim().length < 3} onClick={requestHuman}>
          {busy ? '正在保存…' : pending ? '用原请求重试' : '请求人工协助'}
        </button>
      </div>}
    </article>)}
    {result && <p role="status">{result}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}
