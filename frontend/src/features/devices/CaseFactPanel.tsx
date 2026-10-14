import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import {
  ApiFailure, type Actor, type Device, type DeviceFact, type ServiceCase,
  archiveCaseFact, createCandidateFact, listCaseFactReview, retractFact, verifyFact,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'

type PendingCandidate = { client_fact_id: string, expected_device_revision: number,
  fact_key: string, value: string, source_case_id: string }

function readPending(key: string): PendingCandidate | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (!value || typeof value !== 'object') return null
    const row = value as Partial<PendingCandidate>
    return typeof row.client_fact_id === 'string' && typeof row.source_case_id === 'string' &&
      typeof row.fact_key === 'string' && typeof row.value === 'string' &&
      Number.isSafeInteger(row.expected_device_revision) ? row as PendingCandidate : null
  } catch { return null }
}

function savePending(key: string, item: PendingCandidate | null) {
  try {
    if (item) sessionStorage.setItem(key, JSON.stringify(item))
    else sessionStorage.removeItem(key)
  } catch { /* Same-page retry stays available in state. */ }
}

export function CaseFactPanel({ actor, device, cases }: {
  actor: Actor, device: Device, cases: ServiceCase[] | undefined,
}) {
  const queryClient = useQueryClient()
  const key = `serviceos:case-fact:${actor.tenant_id}:${actor.actor_id}:${device.id}`
  const [pending, setPending] = useState<PendingCandidate | null>(() => readPending(key))
  const [caseId, setCaseId] = useState('')
  const [factKey, setFactKey] = useState('')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const review = useQuery({ queryKey: queryKeys.caseFactReview(actor.tenant_id, actor.actor_id, device.id),
    queryFn: () => listCaseFactReview(device.id), refetchInterval: 10_000 })

  useEffect(() => {
    if (pending && review.data?.some(item => item.client_fact_id === pending.client_fact_id)) {
      setPending(null); savePending(key, null)
      setNotice('已在服务器记录中找到上次提交的候选事实。')
    }
  }, [pending, review.data, key])

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.device(actor.tenant_id, actor.actor_id, device.id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.caseFactReview(actor.tenant_id, actor.actor_id, device.id) }),
    ])
  }

  async function sendCandidate(item: PendingCandidate) {
    setBusy(true); setError(''); setNotice('')
    try {
      await createCandidateFact(device.id, item)
      setPending(null); savePending(key, null)
      setFactKey(''); setValue('')
      setNotice('候选事实已保存，需客服核验后再考虑归档。')
      await refresh()
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        setPending(null); savePending(key, null)
        await refresh()
      }
    } finally { setBusy(false) }
  }

  function startCandidate() {
    if (pending || !caseId || !/^[a-z][a-z0-9_]+$/.test(factKey) || !value.trim()) return
    const item: PendingCandidate = { client_fact_id: crypto.randomUUID(),
      expected_device_revision: device.revision, fact_key: factKey,
      value: value.trim(), source_case_id: caseId }
    setPending(item); savePending(key, item); void sendCandidate(item)
  }

  async function decide(fact: Pick<DeviceFact, 'id' | 'revision' | 'source_case_id'>,
    operation: 'verify' | 'archive' | 'retract') {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      if (operation === 'archive') {
        const sourceCase = cases?.find(item => item.id === fact.source_case_id)
        if (!sourceCase) throw new Error('来源案例尚未加载，请刷新后重试。')
        await archiveCaseFact(sourceCase.id, device.id, fact.id, {
          expected_case_version: sourceCase.version, expected_device_revision: device.revision,
          expected_fact_revision: fact.revision,
        })
        setNotice('已核验事实归档到长期设备档案。')
      } else {
        const body = { expected_device_revision: device.revision,
          expected_fact_revision: fact.revision, reason: reason.trim() }
        if (operation === 'verify') {
          await verifyFact(device.id, fact.id, body)
          setNotice('事实已由客服核验，待来源案例解决后方可归档。')
        } else {
          await retractFact(device.id, fact.id, body)
          setNotice('事实已撤销，不再作为可信设备事实展示。')
        }
      }
      await refresh()
    } catch (failure) {
      setError(readableError(failure))
      await refresh()
    } finally { setBusy(false) }
  }

  return <section className="device-fact-workflow" aria-label="案例事实归档">
    <h3>案例事实归档</h3>
    <p className="muted">从关联案例记录候选事实，客服核验后，仅在案例解决时归档。模型推测不会自动进入长期档案。</p>
    <label>来源案例 <select value={caseId} disabled={busy || Boolean(pending)}
      onChange={event => setCaseId(event.target.value)}>
      <option value="">请选择关联案例</option>
      {cases?.map(item => <option key={item.id} value={item.id}>{item.problem_text} · #{item.id.slice(0, 8)}</option>)}
    </select></label>
    <label>事实字段 <input value={factKey} maxLength={120} disabled={busy || Boolean(pending)}
      placeholder="例如 port_type" onChange={event => setFactKey(event.target.value)} /></label>
    <label>核对到的内容 <input value={value} maxLength={500} disabled={busy || Boolean(pending)}
      onChange={event => setValue(event.target.value)} /></label>
    <button type="button" disabled={busy || Boolean(pending) || !caseId ||
      !/^[a-z][a-z0-9_]+$/.test(factKey) || !value.trim()} onClick={startCandidate}>保存候选事实</button>
    {pending && <p role="status">上次提交结果尚未确认，保留原事实编号。
      <button type="button" disabled={busy} onClick={() => void sendCandidate(pending)}>用原编号重试</button></p>}
    <h4>待核验与待归档</h4>
    {review.isPending && <p>正在加载事实记录…</p>}
    {review.isError && <p className="form-error" role="alert">{readableError(review.error)}</p>}
    {review.data?.length === 0 && <p>暂无待处理的案例来源事实。</p>}
    {(review.data?.length || device.verified_facts?.some(fact => fact.source_case_id)) ? <label>核验或撤销原因 <input value={reason} maxLength={1000}
      disabled={busy} onChange={event => setReason(event.target.value)} /></label> : null}
    <ul>{review.data?.map(fact => {
      const sourceCase = cases?.find(item => item.id === fact.source_case_id)
      return <li key={fact.id}>
        <strong>{fact.fact_key}</strong>：{typeof fact.value === 'string' ? fact.value : JSON.stringify(fact.value)}
        <small>来源案例 #{fact.source_case_id?.slice(0, 8)} · {fact.validity === 'CANDIDATE' ? '待客服核验' : '已核验，待归档'}</small>
        {fact.validity === 'CANDIDATE' && <button type="button" disabled={busy || reason.trim().length < 3}
          onClick={() => void decide(fact, 'verify')}>核验事实</button>}
        {fact.validity === 'VERIFIED' && <button type="button" disabled={busy || sourceCase?.status !== 'RESOLVED'}
          onClick={() => void decide(fact, 'archive')}>归档到设备</button>}
        {fact.validity === 'VERIFIED' && sourceCase?.status !== 'RESOLVED' && <small>来源案例解决后才可归档</small>}
      </li>
    })}</ul>
    {device.verified_facts?.some(fact => fact.source_case_id) && <>
      <h4>撤销已归档事实</h4>
      <ul>{device.verified_facts.filter(fact => fact.source_case_id).map(fact => <li key={fact.id}>
        {fact.fact_key}：{typeof fact.value === 'string' ? fact.value : JSON.stringify(fact.value)}
        <button type="button" disabled={busy || reason.trim().length < 3}
          onClick={() => void decide(fact, 'retract')}>撤销事实</button>
      </li>)}</ul>
    </>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}
