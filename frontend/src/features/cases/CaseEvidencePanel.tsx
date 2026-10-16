import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import {
  ApiFailure, type Actor, type ServiceCase, listCaseEvidence, readCaseEvidenceImage, uploadCaseEvidence,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'

type PendingUpload = { id: string, digest: string, caseVersion: number, visibility: 'PUBLIC' | 'INTERNAL' }
const maxBytes = 10 * 1024 * 1024 // Current proposed limit; the server remains authoritative.
const allowed = ['image/jpeg', 'image/png', 'image/webp']

function readPending(key: string): PendingUpload | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (!value || typeof value !== 'object') return null
    const item = value as Partial<PendingUpload>
    if (typeof item.id !== 'string' || typeof item.digest !== 'string' ||
      !Number.isSafeInteger(item.caseVersion) || !['PUBLIC', 'INTERNAL'].includes(item.visibility ?? '')) return null
    return item as PendingUpload
  } catch { return null }
}

function savePending(key: string, value: PendingUpload | null) {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value))
    else sessionStorage.removeItem(key)
  } catch { /* A same-page retry still keeps the React state. */ }
}

async function digestFile(file: File): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('')
}

export function CaseEvidencePanel({ actor, serviceCase }: { actor: Actor, serviceCase: ServiceCase }) {
  const caseId = serviceCase.id
  const queryClient = useQueryClient()
  const pendingKey = `serviceos:evidence:${actor.tenant_id}:${actor.actor_id}:${caseId}`
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [visibility, setVisibility] = useState<'PUBLIC' | 'INTERNAL'>(() => readPending(pendingKey)?.visibility ?? 'PUBLIC')
  const [pending, setPending] = useState<PendingUpload | null>(() => readPending(pendingKey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState<{ id: string, url: string } | null>(null)
  const evidence = useInfiniteQuery({
    queryKey: queryKeys.caseEvidence(actor.tenant_id, actor.actor_id, caseId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listCaseEvidence(caseId, pageParam ?? undefined),
    getNextPageParam: page => page.next_cursor,
    refetchInterval: 5_000,
  })
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url) }, [preview])
  useEffect(() => {
    if (pending && evidence.data?.pages.some(page => page.items.some(item => item.client_evidence_id === pending.id))) {
      setPending(null)
      savePending(pendingKey, null)
      setNotice('已在服务器记录中找到上次上传的图片。')
    }
  }, [evidence.data, pending, pendingKey])

  async function submit() {
    if (!file || busy) return
    setError(''); setNotice('')
    if (!allowed.includes(file.type) || file.size === 0 || file.size > maxBytes) {
      setError('请选择不超过 10 MiB 的 JPEG、PNG 或 WebP 图片。'); return
    }
    setBusy(true)
    try {
      const digest = await digestFile(file)
      if (pending && digest !== pending.digest) {
        setError('上次上传结果尚未确认，请重新选择同一张图片并使用原编号重试。'); return
      }
      const attempt = pending ?? { id: crypto.randomUUID(), digest,
        caseVersion: serviceCase.version, visibility }
      if (!pending) { setPending(attempt); savePending(pendingKey, attempt) }
      await uploadCaseEvidence(caseId, file, attempt.id, attempt.caseVersion, attempt.visibility)
      setPending(null); savePending(pendingKey, null); setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      setNotice('图片已受理，等待服务端结构检查；通过前无法查看。')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.caseEvidence(actor.tenant_id, actor.actor_id, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) }),
      ])
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        setPending(null); savePending(pendingKey, null)
        await queryClient.invalidateQueries({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, caseId) })
      }
    } finally { setBusy(false) }
  }

  async function show(id: string) {
    setError('')
    try {
      const blob = await readCaseEvidenceImage(caseId, id)
      setPreview({ id, url: URL.createObjectURL(blob) })
    } catch (failure) { setError(readableError(failure)) }
  }

  const rows = evidence.data?.pages.flatMap(page => page.items) ?? []
  return <section id="case-evidence" className="case-evidence" aria-label="案例图片证据">
    <h2>图片证据</h2>
    <p>图片受理后由服务端检查结构。检查通过仅表示文件可安全展示，不代表设备事实或问题已核验。</p>
    <label className="upload-field">选择图片 <small>JPEG、PNG 或 WebP，单张不超过 10 MiB</small><input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" disabled={busy}
      onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
    {actor.kind === 'STAFF' && <label>可见范围 <select value={visibility} disabled={busy || Boolean(pending)}
      onChange={event => setVisibility(event.target.value as 'PUBLIC' | 'INTERNAL')}>
      <option value="PUBLIC">客户与客服可见</option><option value="INTERNAL">仅客服可见</option>
    </select></label>}
    <button type="button" disabled={!file || busy || serviceCase.status === 'CLOSED'} onClick={() => void submit()}>
      {pending ? '用原编号重试上传' : '提交图片'}</button>
    {pending && <p role="status">上次上传结果尚未确认。请重新选择同一张图片，再用原编号重试；也可刷新下方列表核对。</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {evidence.isPending && <p>正在读取图片记录…</p>}
    {evidence.isError && <p className="form-error" role="alert">{readableError(evidence.error)}</p>}
    {evidence.isSuccess && rows.length === 0 && <p>暂无图片证据。</p>}
    <ul className="case-evidence-list">{rows.map(item => <li key={item.id}>
      <div><strong>图片 #{item.id.slice(0, 8)}</strong> · {item.visibility === 'INTERNAL' ? '仅客服' : '客户可见'}
        · {item.inspection_status === 'PENDING' ? '待检查' : item.inspection_status === 'CLEAN' ? '结构检查通过' : '结构检查拒绝'}</div>
      <small>{item.media_type} · {Math.ceil(item.byte_size / 1024)} KiB · 设备事实{item.verification === 'VERIFIED' ? '已核验' : '未核验'}</small>
      {item.inspection_status === 'CLEAN' && <button type="button" onClick={() => void show(item.id)}>查看图片</button>}
    </li>)}</ul>
    {evidence.hasNextPage && <button type="button" disabled={evidence.isFetchingNextPage}
      onClick={() => void evidence.fetchNextPage()}>加载更多图片</button>}
    {preview && <div className="case-evidence-preview" role="dialog" aria-label={`图片 ${preview.id.slice(0, 8)}`}>
      <button type="button" onClick={() => setPreview(null)}>关闭图片</button>
      <img src={preview.url} alt={`案例图片证据 ${preview.id.slice(0, 8)}`} />
    </div>}
  </section>
}
