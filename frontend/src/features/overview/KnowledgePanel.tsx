import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { BookUp, RefreshCw } from 'lucide-react'
import { type Actor, listKnowledgeDocuments, reprocessKnowledgeDocument, uploadKnowledgeDocument } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'

const ACCEPT = '.md,.markdown,.txt,.xlsx,.csv,.jsonl'

export function KnowledgePanel({ actor }: { actor: Actor }) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const documents = useQuery({
    queryKey: queryKeys.knowledge(actor.tenant_id, actor.actor_id),
    queryFn: listKnowledgeDocuments,
    refetchInterval: 5_000,
  })
  const upload = useMutation({
    mutationFn: () => uploadKnowledgeDocument(file as File, title),
    onSuccess: () => {
      setFile(null)
      setTitle('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledge(actor.tenant_id, actor.actor_id) })
    },
  })
  const reprocess = useMutation({
    mutationFn: (id: string) => reprocessKnowledgeDocument(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.knowledge(actor.tenant_id, actor.actor_id) }),
  })
  const canReprocess = actor.role === 'SUPERVISOR' || actor.role === 'ADMIN'
  return <section className="surface knowledge-panel">
    <div className="table-toolbar"><span>知识文档管道</span><small>上传后自动转换、切片、向量化；仅内部参考</small></div>
    <form className="knowledge-upload" onSubmit={event => { event.preventDefault(); if (file) upload.mutate() }}>
      <label className="search-field"><BookUp size={17} /><span className="visually-hidden">选择知识文件</span>
        <input type="file" accept={ACCEPT} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
      <label className="search-field"><span className="visually-hidden">知识标题</span>
        <input placeholder="标题（可选）" value={title} maxLength={200} onChange={event => setTitle(event.target.value)} /></label>
      <button type="submit" disabled={!file || upload.isPending}>上传并入队</button>
    </form>
    {upload.isError && <p className="form-error" role="alert">{readableError(upload.error)}</p>}
    {upload.data?.deduplicated && <p className="empty-note">同一内容已存在，返回既有文档（未重复入队）。</p>}
    {reprocess.isError && <p className="form-error" role="alert">{readableError(reprocess.error)}</p>}
    {documents.isPending && <p className="empty-note">正在读取知识文档…</p>}
    {documents.isError && <p className="form-error" role="alert">{readableError(documents.error)} <button onClick={() => void documents.refetch()}>重试</button></p>}
    <div className="table-scroll" role="region" aria-label="知识文档列表" tabIndex={0}><table className="case-table"><thead><tr><th>文档</th><th>来源</th><th>状态</th><th>版本</th><th><span className="visually-hidden">操作</span></th></tr></thead>
      <tbody>{documents.data?.items.map(item => <tr key={item.document_id}>
        <td>{item.title}<small>{item.filename ?? item.document_id.slice(0, 8)}{item.error_code ? `　·　${item.error_code}` : ''}</small></td>
        <td><small>{item.source_kind}</small></td>
        <td><StatusBadge value={item.status} /></td>
        <td><small>v{item.current_version}</small></td>
        <td>{item.status === 'FAILED' && canReprocess
          ? <button type="button" aria-label={`重新入队 ${item.title}`} onClick={() => reprocess.mutate(item.document_id)} disabled={reprocess.isPending}><RefreshCw size={16} /></button>
          : null}</td>
      </tr>)}</tbody></table></div>
    {!documents.isPending && !documents.isError && (documents.data?.items.length ?? 0) === 0
      && <div className="overview-empty"><BookUp size={30} /><h3>暂无知识文档</h3><p>支持 md/txt/xlsx/csv/jsonl，单文件 ≤10MB。</p></div>}
    <p className="table-foot">状态为服务器真实管道进度；EMBEDDED/STORED 后进入 Agent 可检索范围。</p>
  </section>
}
