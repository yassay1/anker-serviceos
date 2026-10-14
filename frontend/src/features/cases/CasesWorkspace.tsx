import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ApiFailure, type Actor, type CaseAction, type ServiceCase,
  decideActionApproval, listActionApprovals, listCaseActions, listCases, readCase, requestMockAction,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
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
      action_kind: 'MOCK_SERVICE_REQUEST' as const, reason: reason.trim() }
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
      <div><strong>模拟服务请求 #{action.id.slice(0, 8)}</strong> <StatusBadge value={action.status} /></div>
      {actor.kind === 'STAFF' && action.reason && <p>申请原因：{action.reason}</p>}
      {action.receipt ? <p>模拟回执：{action.receipt.external_reference} · {action.receipt.result === 'SUCCEEDED' ? '模拟操作成功' : '模拟操作失败'}</p>
        : action.status === 'UNKNOWN' ? <p>结果待对账。系统只查询原操作，不会重新提交。</p>
          : <p>尚无模拟回执；审批状态不代表执行成功。</p>}
    </article>)}
    {actor.kind === 'STAFF' && <>
      <h3>发起模拟请求</h3>
      <label>申请原因 <input value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} disabled={busy || Boolean(pending)} /></label>
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

export function CasesWorkspace({ actor }: { actor: Actor }) {
  const { id } = useParams<{ id: string }>()
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases })
  const selected = useQuery({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, id ?? ''),
    queryFn: () => readCase(id!), enabled: Boolean(id), refetchInterval: 10_000 })
  return <section className="cases-page" aria-label="服务案例">
    <header><h1>服务案例</h1><p>查看服务进度与模拟售后动作。案例与会话、设备档案分别保存。</p></header>
    {cases.isPending && <p>正在读取案例…</p>}
    {cases.isError && <p className="form-error" role="alert">{readableError(cases.error)}</p>}
    {cases.data?.length === 0 && <p>当前账号暂无服务案例。</p>}
    <div className="cases-layout"><nav aria-label="案例列表"><ul>{cases.data?.map(row =>
      <li key={row.id}><Link to={`/cases/${row.id}`} aria-current={row.id === id ? 'page' : undefined}>{row.problem_text} · #{row.id.slice(0, 8)}</Link></li>
    )}</ul></nav><div className="case-detail">
      {!id && <p>选择一个案例查看详情。</p>}
      {id && selected.isPending && <p>正在读取案例详情…</p>}
      {id && selected.isError && <p className="form-error" role="alert">{readableError(selected.error)}</p>}
      {selected.data && <><h2>{selected.data.problem_text}</h2><p><StatusBadge value={selected.data.status} /> · 版本 {selected.data.version}</p>
        <ActionPanel key={`${actor.actor_id}:${selected.data.id}`} actor={actor} serviceCase={selected.data} /></>}
    </div></div>
  </section>
}
