import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { components } from '../../api/schema'
import {
  ApiFailure, type Actor, type ServiceCase, listCaseActions, listCaseVerifications,
  readResolutionContract, recordCaseVerification,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'

type VerificationBody = components['schemas']['VerificationRequest']

function readPending(key: string): VerificationBody | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (!value || typeof value !== 'object') return null
    const body = value as Partial<VerificationBody>
    return typeof body.client_verification_id === 'string' &&
      Number.isSafeInteger(body.expected_case_version) &&
      Number.isSafeInteger(body.expected_resolution_contract_version) &&
      ['WORKING', 'NOT_WORKING', 'UNCERTAIN'].includes(body.observed_result ?? '') &&
      typeof body.note === 'string' ? body as VerificationBody : null
  } catch { return null }
}

function savePending(key: string, value: VerificationBody | null) {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value))
    else sessionStorage.removeItem(key)
  } catch { /* Same-page retry remains available through React state. */ }
}

const observationLabel = { WORKING: '已恢复', NOT_WORKING: '仍未解决', UNCERTAIN: '还需观察' }
const decisionLabel = { PENDING: '待核验', VERIFIED_RESOLVED: '已核验解决', NOT_RESOLVED: '未解决，继续服务' }

export function VerificationPanel({ actor, serviceCase }: { actor: Actor, serviceCase: ServiceCase }) {
  const caseId = serviceCase.id
  const queryClient = useQueryClient()
  const pendingKey = `serviceos:verification:${actor.tenant_id}:${actor.actor_id}:${caseId}`
  const [pending, setPending] = useState<VerificationBody | null>(() => readPending(pendingKey))
  const [observedResult, setObservedResult] = useState<VerificationBody['observed_result'] | ''>('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const actions = useQuery({ queryKey: queryKeys.caseActions(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => listCaseActions(caseId), refetchInterval: 5_000 })
  const hasAction = Boolean(actions.data?.length)
  const latestAction = actions.data?.at(-1)
  const contract = useQuery({ queryKey: queryKeys.resolutionContract(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => readResolutionContract(caseId), enabled: hasAction })
  const verifications = useQuery({ queryKey: queryKeys.caseVerifications(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => listCaseVerifications(caseId), enabled: hasAction, refetchInterval: 5_000 })

  useEffect(() => {
    if (pending && verifications.data?.some(item => item.client_verification_id === pending.client_verification_id)) {
      setPending(null); savePending(pendingKey, null)
      setNotice('已在服务器记录中找到上次提交的核验结果。')
    }
  }, [pending, pendingKey, verifications.data])

  async function submit(body: VerificationBody) {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await recordCaseVerification(caseId, body)
      setPending(null); savePending(pendingKey, null)
      setNote('')
      setNotice(result.decision === 'VERIFIED_RESOLVED' ? '客户确认已保存，案例已核验解决。'
        : result.decision === 'NOT_RESOLVED' ? '未解决的反馈已保存，案例继续处理。'
          : '观察结果已保存，尚未满足解决条件。')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.caseVerifications(actor.tenant_id, actor.actor_id, caseId) }),
      ])
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        setPending(null); savePending(pendingKey, null)
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) }),
          queryClient.invalidateQueries({ queryKey: queryKeys.resolutionContract(actor.tenant_id, actor.actor_id, caseId) }),
        ])
      }
    } finally { setBusy(false) }
  }

  function start() {
    if (pending || !contract.data || !observedResult) return
    const body: VerificationBody = {
      client_verification_id: crypto.randomUUID(), expected_case_version: serviceCase.version,
      expected_resolution_contract_version: contract.data.version, observed_result: observedResult,
      evidence_ids: [], note: note.trim(),
    }
    setPending(body); savePending(pendingKey, body)
    void submit(body)
  }

  const canConfirmWorking = latestAction?.status === 'SUCCEEDED' && latestAction.receipt?.result === 'SUCCEEDED'
  return <section className="case-verification" aria-label="结果核验">
    <h2>结果核验</h2>
    {!hasAction && <p>此案例尚无模拟售后动作，暂无对应的解决条件。</p>}
    {contract.isError && <p className="form-error" role="alert">{readableError(contract.error)}</p>}
    {contract.data && <><p>本次解决条件：</p><ol>{contract.data.conditions.map(condition => <li key={condition}>{condition}</li>)}</ol></>}
    {hasAction && <p>当前模拟动作：{latestAction?.status === 'SUCCEEDED' ? '收到成功回执' :
      latestAction?.status === 'FAILED' ? '执行失败' : latestAction?.status === 'REJECTED' ? '审批拒绝' : '尚无成功回执'}。
      模拟动作完成后仍需客户确认问题已解决。</p>}
    {verifications.data?.length === 0 && <p>尚无客户观察记录。</p>}
    {verifications.isError && <p className="form-error" role="alert">{readableError(verifications.error)}</p>}
    <ul>{verifications.data?.map(item => <li key={item.id}>
      {observationLabel[item.observed_result]} · {decisionLabel[item.decision]} · {new Date(item.created_at).toLocaleString()}
      {item.note && <small>客户说明：{item.note}</small>}
    </li>)}</ul>
    {actor.kind === 'CUSTOMER' && hasAction && serviceCase.status !== 'RESOLVED' && serviceCase.status !== 'CLOSED' && <>
      <h3>告诉我们处理结果</h3>
      <label>现在的实际情况 <select value={observedResult} disabled={busy || Boolean(pending)}
        onChange={event => setObservedResult(event.target.value as VerificationBody['observed_result'] | '')}>
        <option value="">请选择实际结果</option>
        <option value="WORKING">问题已解决</option><option value="NOT_WORKING">仍未解决</option>
        <option value="UNCERTAIN">还需观察</option>
      </select></label>
      {observedResult === 'WORKING' && !canConfirmWorking && <p>模拟动作尚无成功回执；请等待结果，或反馈仍未解决。</p>}
      <label>补充说明 <textarea value={note} maxLength={2000} disabled={busy || Boolean(pending)}
        onChange={event => setNote(event.target.value)} /></label>
      <button type="button" disabled={busy || Boolean(pending) || !contract.data || !observedResult ||
        (observedResult === 'WORKING' && !canConfirmWorking)} onClick={start}>保存观察结果</button>
    </>}
    {pending && <p role="status">上次提交结果尚未确认，保留原核验编号。
      <button type="button" disabled={busy} onClick={() => void submit(pending)}>用原编号重试</button></p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}
