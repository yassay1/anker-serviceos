import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { ApiFailure, type Actor, type ServiceCase, attachCaseConversation, createServiceCase, listCases, readCase } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { CaseEvidencePanel } from '../cases/CaseEvidencePanel'

export function ConversationAttachments({ actor, conversationId, customerId, initialProblem, relatedCaseIds, initialFiles, onClose }: {
  actor: Actor, conversationId: string, customerId: string, initialProblem: string,
  relatedCaseIds: string[], initialFiles?: File[], onClose: () => void,
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const locked = useRef(false)
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(relatedCaseIds[0] ?? '')
  const [problem, setProblem] = useState(initialProblem.slice(0, 8000))
  const [attached, setAttached] = useState<ServiceCase | null>(null)
  const [created, setCreated] = useState<ServiceCase | null>(null)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases })
  const currentCase = useQuery({
    queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, attached?.id ?? ''),
    queryFn: () => readCase(attached!.id), enabled: Boolean(attached),
  })
  useEffect(() => {
    dialog.current?.showModal()
    return () => dialog.current?.close()
  }, [])

  async function prepare(makeNew: boolean) {
    if (locked.current) return
    locked.current = true
    setBusy(true); setError('')
    let creating = false
    try {
      let serviceCase = makeNew ? created : null
      if (makeNew && !serviceCase) {
        creating = true
        serviceCase = await createServiceCase({ problem_text: problem.trim(),
          ...(actor.kind === 'STAFF' ? { customer_id: customerId } : {}) })
        setCreated(serviceCase)
        creating = false
      }
      if (!serviceCase) serviceCase = await readCase(selectedId)
      const linked = await attachCaseConversation(serviceCase.id, conversationId, serviceCase.version)
      setAttached(linked)
      await queryClient.invalidateQueries({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id) })
    } catch (failure) {
      setError(readableError(failure))
      if (creating && !(failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500)) {
        setUncertain(true)
        setError('创建结果尚未确认。请刷新案例列表，选择可能已创建的案例，避免重复提交。')
      }
    } finally { locked.current = false; setBusy(false) }
  }

  const options = cases.data?.filter(item => item.customer_id === customerId && item.status !== 'CLOSED') ?? []
  return <dialog ref={dialog} className="conversation-attachments" aria-labelledby="attachment-title" onCancel={onClose}>
    <header><h2 id="attachment-title">上传问题图片</h2><button type="button" onClick={onClose} aria-label="关闭图片上传"><X size={18} /></button></header>
    <p>图片保存在你的服务案例中，后续人工客服也能查看。仅支持 JPEG、PNG、WebP；用于 AI 看图时请选不超过 2 MiB 的清晰照片。</p>
    {attached ? <>
      <p className="attachment-hint">已关联案例：{attached.problem_text}。上传并通过检查后，返回对话发送"请帮我看看这张图片"。</p>
      <CaseEvidencePanel actor={actor} serviceCase={currentCase.data ?? attached} initialFiles={initialFiles} />
      <button type="button" onClick={onClose}>返回对话</button>
    </> : <>
      {initialFiles && initialFiles.length > 0 && <p className="attachment-hint">已携带 {initialFiles.length} 张图片：关联或创建案例后自动上传。</p>}
      <label>选择已有服务案例<select value={selectedId} disabled={busy} onChange={event => setSelectedId(event.target.value)}>
        <option value="">请选择案例</option>{options.map(item => <option key={item.id} value={item.id}>{item.problem_text.slice(0, 40)} · #{item.id.slice(0, 8)}</option>)}
      </select></label>
      <div className="attachment-actions"><button type="button" disabled={busy || !selectedId} onClick={() => void prepare(false)}>关联此案例并选择图片</button>
        <button type="button" disabled={busy || cases.isFetching} onClick={() => void cases.refetch()}>刷新案例列表</button></div>
      <div className="attachment-new"><label>还没有合适的案例？确认问题描述后新建<textarea maxLength={8000} rows={2} value={problem} disabled={busy || Boolean(created)} onChange={event => setProblem(event.target.value)} /></label>
        <button type="button" disabled={busy || uncertain || !problem.trim()} onClick={() => void prepare(true)}>
          {busy ? '正在处理…' : created ? '继续关联刚创建的案例' : '确认创建服务案例并上传图片'}</button></div>
    </>}
    {cases.isPending && <p role="status">正在读取可用案例…</p>}
    {cases.isError && <p className="form-error" role="alert">{readableError(cases.error)}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </dialog>
}
