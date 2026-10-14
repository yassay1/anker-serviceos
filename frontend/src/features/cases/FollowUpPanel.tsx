import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { components } from '../../api/schema'
import {
  ApiFailure, type Actor, type ServiceCase, listFollowUpConsents, listFollowUps,
  recordFollowUpConsent, scheduleFollowUp,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'

type ConsentBody = components['schemas']['FollowUpConsentRequest']
type ScheduleBody = components['schemas']['FollowUpRequest']
type Pending = { kind: 'consent', body: ConsentBody } | { kind: 'schedule', body: ScheduleBody }

function readPending(key: string): Pending | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (!value || typeof value !== 'object') return null
    const item = value as Partial<Pending>
    if (item.kind !== 'consent' && item.kind !== 'schedule') return null
    if (!item.body || typeof item.body !== 'object') return null
    return item as Pending
  } catch { return null }
}

function savePending(key: string, value: Pending | null) {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value))
    else sessionStorage.removeItem(key)
  } catch { /* The same-page retry stays available in state. */ }
}

export function FollowUpPanel({ actor, serviceCase }: { actor: Actor, serviceCase: ServiceCase }) {
  const caseId = serviceCase.id
  const queryClient = useQueryClient()
  const key = `serviceos:follow-up:${actor.tenant_id}:${actor.actor_id}:${caseId}`
  const [pending, setPending] = useState<Pending | null>(() => readPending(key))
  const [purpose, setPurpose] = useState('')
  const [consentId, setConsentId] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const consents = useQuery({ queryKey: queryKeys.followUpConsents(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => listFollowUpConsents(caseId), refetchInterval: 10_000 })
  const jobs = useQuery({ queryKey: queryKeys.followUps(actor.tenant_id, actor.actor_id, caseId),
    queryFn: () => listFollowUps(caseId), refetchInterval: 10_000 })

  useEffect(() => {
    if (!pending) return
    const found = pending.kind === 'consent'
      ? consents.data?.some(item => item.client_consent_id === pending.body.client_consent_id)
      : jobs.data?.some(item => item.client_follow_up_id === pending.body.client_follow_up_id)
    if (found) {
      setPending(null); savePending(key, null)
      setNotice('已在服务器记录中找到上次提交的回访安排。')
    }
  }, [pending, key, consents.data, jobs.data])

  async function submit(item: Pending) {
    setBusy(true); setError(''); setNotice('')
    try {
      if (item.kind === 'consent') await recordFollowUpConsent(caseId, item.body)
      else await scheduleFollowUp(caseId, item.body)
      setPending(null); savePending(key, null)
      setNotice(item.kind === 'consent' ? '同意已保存，客服现在可以预约此次回访。'
        : '回访已预约；到期后系统会生成客服待办，不会自动联系客户。')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.followUpConsents(actor.tenant_id, actor.actor_id, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.followUps(actor.tenant_id, actor.actor_id, caseId) }),
      ])
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        setPending(null); savePending(key, null)
        await queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) })
      }
    } finally { setBusy(false) }
  }

  function startConsent() {
    if (pending || purpose.trim().length < 3) return
    const item: Pending = { kind: 'consent', body: { client_consent_id: crypto.randomUUID(),
      expected_case_version: serviceCase.version, purpose: purpose.trim() } }
    setPending(item); savePending(key, item); void submit(item)
  }

  function startSchedule() {
    const consent = consents.data?.find(item => item.id === consentId)
    const parsed = new Date(dueAt)
    if (pending || !consent || !dueAt || Number.isNaN(parsed.valueOf()) || parsed <= new Date()) return
    const item: Pending = { kind: 'schedule', body: { client_follow_up_id: crypto.randomUUID(),
      expected_case_version: serviceCase.version, consent_record_id: consent.id,
      due_at: parsed.toISOString(), purpose: consent.purpose } }
    setPending(item); savePending(key, item); void submit(item)
  }

  return <section className="case-verification" aria-label="回访安排">
    <h2>回访安排</h2>
    <p>客户先同意回访目的，客服再预约时间。到期仅提醒客服处理，不自动向客户发送消息。</p>
    {consents.isError && <p className="form-error" role="alert">{readableError(consents.error)}</p>}
    {jobs.isError && <p className="form-error" role="alert">{readableError(jobs.error)}</p>}
    {consents.data?.length === 0 && <p>尚无客户同意记录。</p>}
    <ul>{consents.data?.map(item => <li key={item.id}>客户同意：{item.purpose} · {new Date(item.created_at).toLocaleString()}</li>)}</ul>
    {jobs.data?.length === 0 && <p>尚无预约回访。</p>}
    <ul>{jobs.data?.map(item => <li key={item.id}>{item.purpose} · {new Date(item.due_at).toLocaleString()} ·
      {item.status === 'DUE' ? '已生成客服待办' : item.status === 'SCHEDULED' ? '等待到期' : '已取消'}
      {actor.kind === 'STAFF' && item.task_id && <small>待办 #{item.task_id.slice(0, 8)}</small>}
    </li>)}</ul>
    {actor.kind === 'CUSTOMER' && serviceCase.status !== 'CLOSED' && <>
      <h3>同意一次回访</h3>
      <label>回访目的 <input value={purpose} maxLength={1000} disabled={busy || Boolean(pending)}
        onChange={event => setPurpose(event.target.value)} /></label>
      <button type="button" disabled={busy || Boolean(pending) || purpose.trim().length < 3}
        onClick={startConsent}>同意此目的的回访</button>
    </>}
    {actor.kind === 'STAFF' && serviceCase.status !== 'CLOSED' && <>
      <h3>预约客服回访</h3>
      <label>客户已同意的目的 <select value={consentId} disabled={busy || Boolean(pending)}
        onChange={event => setConsentId(event.target.value)}>
        <option value="">请选择客户同意记录</option>
        {consents.data?.map(item => <option key={item.id} value={item.id}>{item.purpose}</option>)}
      </select></label>
      <label>回访时间 <input type="datetime-local" value={dueAt} disabled={busy || Boolean(pending)}
        onChange={event => setDueAt(event.target.value)} /></label>
      <button type="button" disabled={busy || Boolean(pending) || !consentId || !dueAt ||
        Number.isNaN(new Date(dueAt).valueOf()) || new Date(dueAt) <= new Date()}
        onClick={startSchedule}>保存预约</button>
    </>}
    {pending && <p role="status">上次提交结果尚未确认，保留原编号。
      <button type="button" disabled={busy} onClick={() => void submit(pending)}>用原编号重试</button></p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}
