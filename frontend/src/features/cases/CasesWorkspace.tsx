import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ClipboardList, ShieldCheck, MessageSquare, CheckCircle2, Clock3, Search, ArrowRight, ChevronRight, Package, Sparkles } from 'lucide-react'
import {
  ApiFailure, type Actor, type CaseAction, type ServiceCase,
  decideActionApproval, listActionApprovals, listCaseActions, listCases, readCase, requestMockAction, listDevices, listDeviceCases,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { caseGuidance, isDemoRecord, shortDate } from '../../shared/servicePresentation'
import { CaseEvidencePanel } from './CaseEvidencePanel'
import { VerificationPanel } from './VerificationPanel'
import { FollowUpPanel } from './FollowUpPanel'
import { StaffCasesWorkspace } from './StaffCasesWorkspace'
import { CaseConversationPicker } from '../../shared/CaseConversationPicker'
import {
  type PendingDecision, readPendingMockAction, readPendingMockDecision,
  savePendingMockAction, savePendingMockDecision,
} from './actionRecovery'

function ActionPanel({ actor, serviceCase }: { actor: Actor, serviceCase: ServiceCase }) {
  const queryClient = useQueryClient()
  const caseId = serviceCase.id
  const actionKey = `serviceos:mock-action:${actor.tenant_id}:${actor.actor_id}:${caseId}`
  const decisionKey = `serviceos:mock-decision:${actor.tenant_id}:${actor.actor_id}:${caseId}`
  const [reason, setReason] = useState('')
  const [remedy, setRemedy] = useState<'REPAIR' | 'RESHIP' | 'REFER_SELLER' | 'DECLINE'>('REPAIR')
  const [decisionReason, setDecisionReason] = useState('已核对模拟售后请求')
  const [pending, setPending] = useState(() => readPendingMockAction(actionKey))
  const [pendingDecision, setPendingDecision] = useState(() => readPendingMockDecision(decisionKey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const actions = useQuery({
    queryKey: queryKeys.caseActions(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => listCaseActions(caseId), refetchInterval: 5_000,
  })
  const approvals = useQuery({
    queryKey: queryKeys.caseActionApprovals(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => listActionApprovals(caseId), enabled: actor.kind === 'STAFF', refetchInterval: 5_000,
  })

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.caseActions(actor.tenant_id, actor.actor_id, caseId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.caseActionApprovals(actor.tenant_id, actor.actor_id, caseId) }),
    ])
  }

  async function sendAction(body: NonNullable<typeof pending>) {
    setBusy(true); setError(''); setNotice('')
    try {
      await requestMockAction(caseId, body)
      setPending(null); savePendingMockAction(actionKey, null)
      setReason('')
      setNotice('模拟动作请求已保存，等待另一位有审批权限的客服处理。')
      await refresh()
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) await refresh()
    } finally { setBusy(false) }
  }

  function startAction() {
    if (pending || reason.trim().length < 3) return
    const body = { client_action_id: crypto.randomUUID(), expected_case_version: serviceCase.version,
      action_kind: 'MOCK_SERVICE_REQUEST' as const, remedy_type: remedy, reason: reason.trim() }
    setPending(body); savePendingMockAction(actionKey, body)
    void sendAction(body)
  }

  async function sendDecision(item: PendingDecision) {
    setBusy(true); setError(''); setNotice('')
    try {
      await decideActionApproval(item.approvalId, item.body)
      setPendingDecision(null); savePendingMockDecision(decisionKey, null)
      setNotice(item.body.decision === 'APPROVED' ? '审批已保存，模拟操作等待 Worker 执行。' : '审批已拒绝，模拟操作不会执行。')
      await refresh()
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) await refresh()
    } finally { setBusy(false) }
  }

  function startDecision(approvalId: string, version: number, decision: 'APPROVED' | 'REJECTED') {
    if (pendingDecision || decisionReason.trim().length < 3) return
    const item: PendingDecision = { approvalId, body: {
      decision_id: crypto.randomUUID(), expected_version: version, decision, reason: decisionReason.trim(),
    } }
    setPendingDecision(item); savePendingMockDecision(decisionKey, item)
    void sendDecision(item)
  }

  const byId = new Map((actions.data ?? []).map((action: CaseAction) => [action.id, action]))
  const canApprove = actor.kind === 'STAFF' && ['SUPERVISOR', 'ADMIN'].includes(actor.role ?? '')
  return <section className="case-actions" aria-label="模拟售后动作">
    <h2>模拟售后动作</h2>
    <p>此处只模拟提交售后服务请求，不连接真实 Anker 售后系统。审批通过后仍需等待明确标记的模拟回执。</p>
    {actions.isPending && <p>正在读取动作记录…</p>}
    {actions.isError && <p className="form-error" role="alert">{readableError(actions.error)}</p>}
    {actions.data?.length === 0 && <p>此案例尚无模拟售后动作。</p>}
    {actions.data?.map(action => <article className="case-action-item" key={action.id}>
      <div><strong>模拟服务请求 #{action.id.slice(0, 8)}</strong> <StatusBadge value={action.status} />
        {action.remedy_type && <small>　结局：{action.remedy_type}</small>}
        {actor.kind === 'STAFF' && <small>　申请来源：{action.requested_by ? '客服' : 'Agent'}</small>}</div>
      {actor.kind === 'STAFF' && action.reason && <p>申请原因：{action.reason}</p>}
      {action.receipt ? <p>模拟回执：{action.receipt.external_reference} · {action.receipt.result === 'SUCCEEDED' ? '模拟操作成功' : '模拟操作失败'}</p>
        : action.status === 'UNKNOWN' ? <p>结果待对账。系统只查询原操作，不会重新提交。</p>
          : <p>尚无模拟回执；审批状态不代表执行成功。</p>}
    </article>)}
    {actor.kind === 'STAFF' && <>
      <h3>发起模拟请求</h3>
      <label>申请原因 <input value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} disabled={busy || Boolean(pending)} /></label>
      <label>结局类型 <select value={remedy} onChange={e => setRemedy(e.target.value as typeof remedy)} disabled={busy || Boolean(pending)}>
        <option value="REPAIR">寄修 REPAIR</option>
        <option value="RESHIP">补单 RESHIP</option>
        <option value="REFER_SELLER">引导商家 REFER_SELLER</option>
        <option value="DECLINE">婉拒 DECLINE</option>
      </select></label>
      <button type="button" disabled={busy || Boolean(pending) || reason.trim().length < 3 || ['RESOLVED', 'CLOSED'].includes(serviceCase.status)} onClick={startAction}>提交待审批请求</button>
      {pending && <p role="status">上次提交的结果尚未确认，保留原请求编号。
        <button type="button" disabled={busy} onClick={() => void sendAction(pending)}>用原编号重试</button></p>}
      <h3>动作审批</h3>
      {approvals.isError && <p className="form-error" role="alert">{readableError(approvals.error)}</p>}
      {approvals.data?.length === 0 && <p>暂无动作审批。</p>}
      {canApprove && <label>审批原因 <input value={decisionReason} maxLength={1000} onChange={e => setDecisionReason(e.target.value)} disabled={busy || Boolean(pendingDecision)} /></label>}
      {approvals.data?.map(approval => {
        const action = byId.get(approval.action_id)
        return <div className="case-approval-item" key={approval.id}>
          <span>模拟请求 #{approval.action_id.slice(0, 8)} · <StatusBadge value={approval.status} /></span>
          {approval.status === 'PENDING' && canApprove && action?.requested_by !== actor.actor_id &&
            <span><button type="button" disabled={busy || Boolean(pendingDecision) || decisionReason.trim().length < 3} onClick={() => startDecision(approval.id, approval.version, 'APPROVED')}>批准</button>
              <button type="button" disabled={busy || Boolean(pendingDecision) || decisionReason.trim().length < 3} onClick={() => startDecision(approval.id, approval.version, 'REJECTED')}>拒绝</button></span>}
          {approval.status === 'PENDING' && action?.requested_by === actor.actor_id && <small>申请人不能自批</small>}
        </div>
      })}
      {pendingDecision && <p role="status">审批结果尚未确认，保留原决定编号。
        <button type="button" disabled={busy} onClick={() => void sendDecision(pendingDecision)}>用原编号重试审批</button></p>}
    </>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}

const finished = (status: string) => ['RESOLVED', 'CLOSED'].includes(status)

export function CasesWorkspace({ actor }: { actor: Actor }) {
  const { id } = useParams<{ id: string }>()
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [previewId, setPreviewId] = useState<string | null>(null)
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases, refetchInterval: 10_000 })
  const selected = useQuery({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, id ?? ''),
    queryFn: () => readCase(id!), enabled: Boolean(id), refetchInterval: 10_000 })
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices })
  const deviceHistories = useQueries({ queries: (devices.data ?? []).map(device => ({
    queryKey: queryKeys.deviceCases(actor.tenant_id, actor.actor_id, device.id),
    queryFn: () => listDeviceCases(device.id),
  })) })
  const relatedDevices = (caseId: string) => (devices.data ?? []).filter((_, index) => deviceHistories[index]?.data?.some(item => item.id === caseId))
  const rows = cases.data ?? []
  const filtered = rows.filter(row => (filter === 'all' || (filter === 'active' ? !finished(row.status) : finished(row.status))) &&
    `${row.problem_text} ${row.id} ${row.user_goal ?? ''}`.toLowerCase().includes(search.trim().toLowerCase()))
  const preview = filtered.find(row => row.id === previewId) ?? filtered[0]
  const record = selected.data
  const guidance = record ? caseGuidance(record.status, actor.kind === 'STAFF') : null
  const supportPath = actor.kind === 'STAFF' ? '/desk' : '/support'

  function deviceLinks(caseId: string) {
    const matches = relatedDevices(caseId)
    if (devices.isError || deviceHistories.some(query => query.isError)) return <span className="muted">关联设备暂时无法读取</span>
    if (devices.isPending || deviceHistories.some(query => query.isPending)) return <span className="muted">正在读取关联设备…</span>
    return matches.length ? matches.map(device => <Link key={device.id} to={`/devices/${device.id}`} className="case-device-link"><DeviceIcon model={device.model} size={17} />{device.model || '型号待确认'}</Link>)
      : <span className="muted"><Package size={16} aria-hidden="true" /> 暂无关联设备档案</span>
  }

  if (actor.kind === 'STAFF' && !id) return <StaffCasesWorkspace actor={actor} rows={rows} loading={cases.isPending}
    error={cases.isError ? readableError(cases.error) : undefined} loaded={cases.isSuccess}
    onRetry={() => void cases.refetch()} relatedDevices={relatedDevices} />

  return <section className={`cases-page ${id ? 'case-detail-page' : 'case-list-page'}`} aria-label="服务案例">
    <header className="page-heading">{id ? <Link className="breadcrumb" to="/cases"><ArrowLeft size={16} />返回我的服务<span>/</span>服务详情</Link> : <><div><h1>我的服务</h1><p>每一次问题都有记录，每一步处理都可回看。</p></div><Link className="button-link primary-button" to={supportPath}><Sparkles size={17} />发起服务咨询</Link></>}</header>
    {!id && <>
      <div className="service-overview" aria-label="服务记录统计">{[
        { key: 'all', title: '全部服务', value: rows.length, icon: ClipboardList },
        { key: 'active', title: '待跟进服务', value: rows.filter(row => !finished(row.status)).length, icon: Clock3 },
        { key: 'done', title: '已解决 / 已关闭', value: rows.filter(row => finished(row.status)).length, icon: CheckCircle2 },
      ].map(({ key, title, value, icon: Icon }) => <button type="button" key={key} className={`service-metric metric-${key}`} aria-pressed={filter === key} onClick={() => setFilter(key)}><span className="round-icon"><Icon size={22} /></span><span><span>{title}</span><strong>{cases.isSuccess ? value : '—'}</strong></span><ChevronRight size={17} /></button>)}</div>
      <div className="services-toolbar"><div className="service-filters" aria-label="筛选已加载的服务">{[['all', '全部服务'], ['active', '待跟进'], ['done', '已结束']].map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div><label className="service-search"><Search size={18} aria-hidden="true" /><span className="visually-hidden">搜索服务记录</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索问题或服务编号" /></label></div>
      {cases.isPending && <div className="service-loading" role="status"><ClipboardList size={30} /><p>正在读取您的服务记录…</p></div>}
      {cases.isError && <div className="service-loading form-error" role="alert"><p>{readableError(cases.error)}</p><button onClick={() => void cases.refetch()}>重新加载服务</button></div>}
      {cases.isSuccess && <div className="services-master-detail"><div className="service-records" aria-label="工单列表">
        <div className="service-list-caption">服务记录 <span>{filtered.length} 条</span></div>
        {filtered.map(row => <article key={row.id} className={`service-record ${preview?.id === row.id ? 'is-selected' : ''}`}>
          <button className="service-record-select" type="button" aria-pressed={preview?.id === row.id} onClick={() => setPreviewId(row.id)}>
            <span className="service-record-top"><span className="service-number">服务 #{row.id.slice(0, 8)}</span><StatusBadge value={row.status} /></span>
            <strong>{row.problem_text}</strong><span className="service-record-goal">{row.user_goal || '服务目标尚待补充，可在会话中继续沟通。'}</span>
            <span className="service-record-bottom"><time dateTime={row.created_at}>{shortDate(row.created_at)} 创建</time>{isDemoRecord(row.problem_text) && <span className="demo-label">演示记录</span>}</span>
          </button><div className="service-record-foot"><span>{caseGuidance(row.status).title}</span><Link to={`/cases/${row.id}`}>查看详情<ChevronRight size={15} /></Link></div>
        </article>)}
        {filtered.length === 0 && <div className="detail-placeholder"><ClipboardList size={38} /><h2>{rows.length ? '没有找到匹配的服务' : '您的服务记录，从这里开始'}</h2><p>{rows.length ? '试试其他关键词，或查看全部服务。' : '描述设备问题后，可在这里回看后续建立的工单。'}</p>{rows.length ? <button onClick={() => { setSearch(''); setFilter('all') }}>查看全部服务</button> : <Link className="button-link primary-button" to={supportPath}>开始服务咨询</Link>}</div>}
      </div><aside className="service-preview-panel" aria-label="工单预览">
        {preview ? <><div className="preview-heading"><h2>服务概览</h2><StatusBadge value={preview.status} /></div><h3>{preview.problem_text}</h3>
          {isDemoRecord(preview.problem_text) && <p className="demo-notice">演示记录 · 模拟处理不代表真实维修结果。</p>}
          <dl className="preview-meta"><div><dt>创建时间</dt><dd>{new Date(preview.created_at).toLocaleString('zh-CN')}</dd></div><div><dt>关联设备</dt><dd className="case-device-links">{deviceLinks(preview.id)}</dd></div><div><dt>服务目标</dt><dd>{preview.user_goal || '尚未补充'}</dd></div></dl>
          <div className={`next-step ${finished(preview.status) ? 'is-complete' : ''}`}><span className="round-icon">{finished(preview.status) ? <CheckCircle2 size={23} /> : <Clock3 size={23} />}</span><div><strong>{caseGuidance(preview.status).title}</strong><p>{caseGuidance(preview.status).body}</p></div></div>
          <Link className="button-link primary-button preview-open" to={`/cases/${preview.id}`}>查看完整服务记录<ArrowRight size={17} /></Link><p className="preview-security"><ShieldCheck size={14} />仅展示当前账号有权查看的信息</p>
        </> : <div className="detail-placeholder"><ShieldCheck size={38} /><h2>服务进展，清晰可查</h2><p>工单中的问题、证据与结果核验，会在这里有序呈现。</p></div>}
      </aside></div>}
    </>}
    {id && <div className="case-detail">
      {selected.isPending && <div className="service-loading" role="status">正在读取服务详情…</div>}
      {selected.isError && <div className="detail-placeholder" role="alert"><h2>暂时无法查看此服务</h2><p>{readableError(selected.error)}</p><button onClick={() => void selected.refetch()}>重新加载详情</button></div>}
      {record && guidance && <>
        <section className="case-record-hero"><span className={`case-record-symbol ${finished(record.status) ? 'is-complete' : ''}`}>{finished(record.status) ? <CheckCircle2 size={34} /> : <ClipboardList size={34} />}</span><div className="case-record-identity"><div className="case-identity-tags"><StatusBadge value={record.status} />{isDemoRecord(record.problem_text) && <span className="demo-label">演示记录</span>}</div><h1>{record.problem_text}</h1><div className="case-record-meta"><span>服务 #{record.id.slice(0, 8)}</span><time dateTime={record.created_at}>{new Date(record.created_at).toLocaleString('zh-CN')} 创建</time><span>记录版本 {record.version}</span></div></div><a className="button-link" href={`#${guidance.anchor}`}>{guidance.action}<ArrowRight size={16} /></a></section>
        {isDemoRecord(record.problem_text) && <p className="case-demo-note"><ShieldCheck size={15} />此工单包含演示信息，模拟售后动作与回执不代表真实 Anker 服务。</p>}
        <div className={`case-next-action ${finished(record.status) ? 'is-complete' : ''}`}><span className="round-icon">{finished(record.status) ? <ShieldCheck size={25} /> : <Clock3 size={25} />}</span><div><strong>{guidance.title}</strong><p>{guidance.body}</p></div></div>
        <div className="case-detail-columns">
          <div className="case-main-column">
            <section id="case-progress" className="case-progress-record"><h2>服务进展</h2><ol><li><span className="timeline-node current" /><div><strong>当前服务状态</strong><p><StatusBadge value={record.status} /></p><small>状态以最新保存的服务记录为准。</small></div></li><li><span className="timeline-node" /><div><strong>问题已提交</strong><p>{new Date(record.created_at).toLocaleString('zh-CN')}</p><small>问题描述与服务目标已保存。</small></div></li></ol></section>
            {finished(record.status) && <div id="case-result"><VerificationPanel key={`verification:${actor.actor_id}:${record.id}`} actor={actor} serviceCase={record} /></div>}
            <section className="case-problem surface"><h2>问题与设备</h2><h3>故障现象</h3><p>{record.problem_text}</p><h3>期望服务目标</h3><p>{record.user_goal || '尚未补充，可在服务会话中继续沟通。'}</p><h3>关联设备档案</h3><div className="case-device-links">{deviceLinks(record.id)}</div></section>
            <ActionPanel key={`${actor.actor_id}:${record.id}`} actor={actor} serviceCase={record} />
          </div>
          <div className="case-side-column">
            <section className="surface service-help"><span className="round-icon"><MessageSquare size={23} /></span><div><h2>继续服务沟通</h2><p>查看此服务记录真实关联的对话；一个服务记录可以关联多段会话。</p></div><CaseConversationPicker key={record.id} actor={actor} serviceCase={record} label="查看关联对话" className="button-link" /></section>
            {!finished(record.status) && <CaseEvidencePanel key={`evidence:${actor.actor_id}:${record.id}`} actor={actor} serviceCase={record} />}
            {!finished(record.status) && <div id="case-result"><VerificationPanel key={`verification:${actor.actor_id}:${record.id}`} actor={actor} serviceCase={record} /></div>}
            <FollowUpPanel key={`follow-up:${actor.actor_id}:${record.id}`} actor={actor} serviceCase={record} />
            {finished(record.status) && <CaseEvidencePanel key={`evidence:${actor.actor_id}:${record.id}`} actor={actor} serviceCase={record} />}
          </div>
        </div>
      </>}
    </div>}
  </section>
}
