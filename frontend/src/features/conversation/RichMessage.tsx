import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, ImagePlus, ShieldAlert, ExternalLink } from 'lucide-react'
import { readCaseEvidenceImage } from '../../api/client'
import type { components } from '../../api/schema'
import './rich-reply.css'

type Reply = Required<components['schemas']['RichReply']>
type Block = components['schemas']['ReplyBlock']
type QuickReply = components['schemas']['QuickReply']
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const text = (value: unknown, limit: number) => typeof value === 'string' && value.length <= limit
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const types = ['summary', 'steps', 'table', 'image', 'image_focus', 'alert', 'timeline', 'status', 'reference', 'actions']
const blockKeys = new Set(['type', 'title', 'text', 'items', 'columns', 'rows', 'case_id', 'evidence_id', 'focus', 'source_id', 'source_url', 'severity', 'entries', 'status_code', 'action'])

function safeSource(url: unknown): url is string {
  if (typeof url !== 'string') return false
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' && !parsed.username && !parsed.password && ['service.anker.com', 'support.eufy.com'].includes(parsed.hostname)
  } catch { return false }
}

function validBlock(value: unknown): value is Block {
  if (!record(value) || Object.keys(value).some(key => !blockKeys.has(key)) || !types.includes(String(value.type)) ||
    !text(value.title ?? '', 120) || !text(value.text ?? '', 2000)) return false
  if (value.status_code != null && !text(value.status_code, 40)) return false
  if (value.case_id != null && !(typeof value.case_id === 'string' && uuid.test(value.case_id))) return false
  if (value.evidence_id != null && !(typeof value.evidence_id === 'string' && uuid.test(value.evidence_id))) return false
  if (value.type === 'steps' && (!Array.isArray(value.items) || !value.items.length || value.items.length > 6 ||
    !value.items.every(item => record(item) && text(item.title, 100) && text(item.description, 500)))) return false
  if (value.type === 'table' && (!Array.isArray(value.columns) || value.columns.length < 2 || value.columns.length > 5 ||
    !value.columns.every(item => text(item, 500)) || !Array.isArray(value.rows) || !value.rows.length || value.rows.length > 8 ||
    !value.rows.every(row => Array.isArray(row) && row.length === (value.columns as unknown[]).length && row.every(cell => text(cell, 500))))) return false
  if (['image', 'image_focus'].includes(String(value.type)) &&
    !(typeof value.case_id === 'string' && uuid.test(value.case_id) && typeof value.evidence_id === 'string' && uuid.test(value.evidence_id))) return false
  if (value.focus != null && (!record(value.focus) || !['x', 'y', 'width', 'height'].every(key => typeof (value.focus as Record<string, unknown>)[key] === 'number' &&
    Number.isFinite((value.focus as Record<string, number>)[key])) ||
    Number(value.focus.x) < 0 || Number(value.focus.y) < 0 || Number(value.focus.width) <= 0 || Number(value.focus.height) <= 0 ||
    Number(value.focus.x) + Number(value.focus.width) > 1 || Number(value.focus.y) + Number(value.focus.height) > 1)) return false
  if (value.type === 'timeline' && (!Array.isArray(value.entries) || value.entries.length > 8 || !value.entries.every(item =>
    record(item) && text(item.label, 500) && text(item.description, 500) && typeof item.time === 'string' && Number.isFinite(Date.parse(item.time)) &&
    ['recorded', 'pending', 'current', 'completed', 'failed'].includes(String(item.state ?? 'recorded'))))) return false
  if (value.type === 'reference' && (!text(value.source_id, 100) || (value.source_url != null && !safeSource(value.source_url)))) return false
  if (value.type === 'actions' && !['view_case', 'upload_evidence', 'request_assistance'].includes(String(value.action))) return false
  if (value.type === 'actions' && value.action !== 'request_assistance' && !(typeof value.case_id === 'string' && uuid.test(value.case_id))) return false
  return true
}

function validReply(value: unknown): value is Reply {
  if (!record(value) || Object.keys(value).some(key => !['schema_version', 'blocks', 'quick_replies'].includes(key)) || value.schema_version !== 1 ||
    !Array.isArray(value.blocks) || value.blocks.length > 8 || !value.blocks.every(validBlock) ||
    !Array.isArray(value.quick_replies) || value.quick_replies.length > 4 || value.quick_replies.length === 1) return false
  const ids = new Set<string>(), messages = new Set<string>()
  return value.quick_replies.every(item => {
    if (!record(item) || Object.keys(item).some(key => !['id', 'label', 'message'].includes(key)) || typeof item.id !== 'string' ||
      !/^[a-zA-Z0-9_-]{1,40}$/.test(item.id) || !text(item.label, 40) || !String(item.label).trim() ||
      !text(item.message, 500) || !String(item.message).trim() || ids.has(item.id) || messages.has(String(item.message))) return false
    ids.add(item.id); messages.add(String(item.message)); return true
  })
}

function InlineText({ value }: { value: string }) {
  return <>{value.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, index) => part.startsWith('**') && part.endsWith('**')
    ? <strong key={index}>{part.slice(2, -2)}</strong> : part.startsWith('`') && part.endsWith('`')
      ? <code key={index}>{part.slice(1, -1)}</code> : part)}</>
}

export function MessageText({ value }: { value: string }) {
  return <div className="rich-prose">{value.split(/\n\s*\n/).map((paragraph, index) => {
    const lines = paragraph.split('\n')
    if (lines.every(line => /^\s*[-*] /.test(line))) return <ul key={index}>{lines.map((line, item) => <li key={item}><InlineText value={line.replace(/^\s*[-*] /, '')} /></li>)}</ul>
    if (lines.every(line => /^\s*\d+[.)、] /.test(line))) return <ol key={index}>{lines.map((line, item) => <li key={item}><InlineText value={line.replace(/^\s*\d+[.)、] /, '')} /></li>)}</ol>
    if (paragraph.startsWith('```')) return <pre key={index}><code>{paragraph.replace(/^```[^\n]*\n?/, '').replace(/```$/, '')}</code></pre>
    return <p key={index}><InlineText value={paragraph.replace(/^#{1,4}\s+/, '')} /></p>
  })}</div>
}

function EvidenceImage({ block }: { block: Block }) {
  const [image, setImage] = useState(''), [error, setError] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    let disposed = false, objectUrl = ''
    setImage(''); setError(false)
    void readCaseEvidenceImage(block.case_id!, block.evidence_id!).then(blob => {
      if (!['image/png', 'image/jpeg', 'image/webp'].includes(blob.type)) throw new Error('Unsupported image')
      if (!disposed) { objectUrl = URL.createObjectURL(blob); setImage(objectUrl) }
    }).catch(() => { if (!disposed) setError(true) })
    return () => { disposed = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [block.case_id, block.evidence_id])
  return <figure className="rich-image">
    {image ? <button type="button" className="rich-image-preview" onClick={() => dialog.current?.showModal()} aria-label="预览上传原图"><img src={image} alt={block.title || '用户上传的图片证据'} loading="lazy" /><span>查看原图 <ExternalLink size={13} /></span></button>
      : <p className="muted">{error ? '图片当前不可访问或尚未通过检查，请进入服务案例查看。' : '正在加载已授权图片…'}</p>}
    <figcaption>{block.text}</figcaption>
    <dialog ref={dialog} className="rich-image-dialog" aria-label="上传图片原图"><button type="button" onClick={() => dialog.current?.close()}>关闭预览</button>
      {image && <><img src={image} alt="用户上传的原始图片" /><a href={image} target="_blank" rel="noopener noreferrer">在新窗口查看原图</a></>}
    </dialog>
  </figure>
}

function QuickReplies({ items, onSelect }: { items: QuickReply[], onSelect: (value: string) => Promise<boolean> }) {
  const clicked = useRef(false)
  const [busy, setBusy] = useState(false)
  async function choose(message: string) {
    if (clicked.current) return
    clicked.current = true; setBusy(true)
    try { await onSelect(message) } finally { setBusy(false) }
  }
  return <div className="quick-replies"><div className="quick-replies-label">你还可以这样问</div><div className="quick-replies-list">
    {items.map(item => <button key={item.id} type="button" className="quick-reply-chip" disabled={busy || clicked.current}
      onClick={() => void choose(item.message)}><span>{item.label}</span><ArrowUpRight size={13} aria-hidden="true" /></button>)}
  </div></div>
}

function ReplySection({ block }: { block: Block }) {
  const heading = block.title && <h4>{block.title}</h4>
  switch (block.type) {
    case 'summary': return <div className="rich-summary">{heading}<MessageText value={block.text ?? ''} /></div>
    case 'steps': return <section className="rich-steps">{heading}<ol>{block.items?.map((item, index) => <li key={index}><span className="rich-step-number" aria-hidden="true">{index + 1}</span><div><strong>{item.title}</strong><p>{item.description}</p></div></li>)}</ol></section>
    case 'table': return <section className="rich-table-section">{heading}<div className="rich-table-scroll" role="region" tabIndex={0} aria-label={block.title || '排查参考表'}><table><thead><tr>{block.columns?.map((column, index) => <th key={index} scope="col">{column}</th>)}</tr></thead><tbody>{block.rows?.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column}><InlineText value={cell} /></td>)}</tr>)}</tbody></table></div><small>排查方向供参考，不等同于已核验的设备故障。</small></section>
    case 'alert': return <aside className={`rich-alert ${block.severity ?? 'info'}`} role={block.status_code === 'POLICY_SAFETY_STOP' ? 'alert' : 'note'}><ShieldAlert size={18} aria-hidden="true" /><div>{heading}<MessageText value={block.text ?? ''} /></div></aside>
    case 'image': case 'image_focus': return <EvidenceImage block={block} />
    case 'status': return <div className="rich-status"><span className={`rich-status-dot ${block.status_code === 'RESOLVED' || block.status_code === 'CLOSED' ? 'done' : ''}`} />{heading}<strong>{block.text}</strong>{block.case_id && <Link to={`/cases/${block.case_id}`}>查看案例 <ArrowUpRight size={13} /></Link>}</div>
    case 'timeline': return <section className="rich-timeline">{heading}<ol>{block.entries?.map((entry, index) => <li key={index} className={`timeline-${entry.state ?? 'recorded'}`}><span className="rich-timeline-dot" /><div><strong>{entry.label}</strong><time dateTime={entry.time}>{new Date(entry.time).toLocaleString('zh-CN')}</time><p>{entry.description}</p></div></li>)}</ol><small>时间为记录创建或核验时间，状态来自当前记录；不推断尚未发生的阶段。</small></section>
    case 'reference': return <div className="rich-reference"><span>资料来源</span>{safeSource(block.source_url) ? <a href={block.source_url} target="_blank" rel="noopener noreferrer">{block.title}<ExternalLink size={12} /></a> : <strong>{block.title}</strong>}<small>{block.text}</small></div>
    case 'actions': return <div className="rich-next-action">{block.action === 'request_assistance'
      ? <button type="button" onClick={() => { document.getElementById('conversation-interactions')?.scrollIntoView({ block: 'center', behavior: 'smooth' }); document.getElementById('conversation-interactions')?.focus() }}>{block.title}<ArrowUpRight size={14} /></button>
      : <Link className="button-link" to={`/cases/${block.case_id}${block.action === 'upload_evidence' ? '#case-evidence' : ''}`}><ImagePlus size={15} />{block.title}</Link>}<small>{block.text}</small></div>
  }
}

export function RichMessage({ fallback, rich, allowQuickReplies, onQuickReply }: {
  fallback: string, rich: unknown, allowQuickReplies: boolean, onQuickReply?: (value: string) => Promise<boolean>
}) {
  if (!validReply(rich)) return <MessageText value={fallback} />
  const blocks = rich.blocks.filter(block => block.type !== 'summary' || block.text?.trim() !== fallback.trim())
  const policyAlerts = blocks.filter(block => block.type === 'alert' && block.status_code === 'POLICY_SAFETY_STOP')
  const remaining = blocks.filter(block => !policyAlerts.includes(block))
  const primary = remaining.slice(0, 3), extra = remaining.slice(3)
  return <div className="rich-reply">
    {policyAlerts.map((block, index) => <ReplySection key={`safety-${index}`} block={block} />)}
    {policyAlerts.length === 0 && <MessageText value={fallback} />}
    {primary.map((block, index) => <ReplySection key={index} block={block} />)}
    {extra.length > 0 && <details className="rich-more"><summary>更多排查依据与资料（{extra.length}）</summary>{extra.map((block, index) => <ReplySection key={index} block={block} />)}</details>}
    {allowQuickReplies && onQuickReply && rich.quick_replies.length > 0 && <QuickReplies items={rich.quick_replies} onSelect={onQuickReply} />}
  </div>
}
