import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, ChevronRight, Power, Wifi, Box, Wrench, Truck, ClipboardList, Sparkles, Headphones, ShieldCheck, MonitorSmartphone } from 'lucide-react'
import { ApiFailure, type Actor, type SendBody, createConversation, listCases, listDevices, listConversations, sendMessage } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { StatusBadge } from '../../shared/StatusBadge'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { isDemoRecord } from '../../shared/servicePresentation'
import { readableError } from '../../shared/errors'
import { MessageComposer } from '../conversation/MessageComposer'
import { ConversationAttachments } from '../conversation/ConversationAttachments'

const categories = [
  { title: '无法开机', description: '没有反应 / 电源问题', icon: Power, prompt: '我的设备无法开机，' },
  { title: '连接异常', description: '无法联网 / 配网失败', icon: Wifi, prompt: '我的设备连接异常，' },
  { title: '功能异常', description: '运行异常 / 效果不佳', icon: Box, prompt: '我的设备功能异常，' },
  { title: '配件问题', description: '配件损坏 / 使用问题', icon: Wrench, prompt: '我想咨询设备配件，' },
  { title: '物流与退换', description: '描述您的售后诉求', icon: Truck, prompt: '我想咨询物流或退换，' },
  { title: '使用咨询', description: '产品使用 / 保养维护', icon: ClipboardList, prompt: '我想了解设备的使用方法，' },
]

export function CustomerHome({ actor }: { actor: Actor }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [draftConversationId, setDraftConversationId] = useState<string | null>(null)
  const [pendingMessage, setPendingMessage] = useState<SendBody | null>(null)
  const [attachmentsFor, setAttachmentsFor] = useState<string | null>(null)
  const operationLock = useRef(false)
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases })
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices })
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations })

  async function ensureDraftConversation() {
    if (draftConversationId) return draftConversationId
    const conversation = await createConversation()
    setDraftConversationId(conversation.id)
    void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
    return conversation.id
  }

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (operationLock.current || busy || !draft.trim()) return
    operationLock.current = true
    setBusy(true); setError('')
    try {
      const conversationId = await ensureDraftConversation()
      const message = pendingMessage ?? {
        client_message_id: crypto.randomUUID(),
        content: [{ type: 'text' as const, text: draft.trim() }],
        visibility: 'PUBLIC' as const,
      }
      if (!pendingMessage) setPendingMessage(message)
      await sendMessage(conversationId, message)
      setPendingMessage(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      navigate(`/support?conversation=${conversationId}`)
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) setPendingMessage(null)
      setError(readableError(failure))
    } finally { operationLock.current = false; setBusy(false) }
  }

  async function openAttachments() {
    if (operationLock.current || busy || pendingMessage) return
    operationLock.current = true
    setBusy(true); setError('')
    try {
      const conversationId = await ensureDraftConversation()
      if (!draft.trim()) setDraft('我上传了一张图片，请帮我看看。')
      setAttachmentsFor(conversationId)
    } catch (failure) { setError(readableError(failure)) }
    finally { operationLock.current = false; setBusy(false) }
  }

  return <div className="customer-home">
    <section className="home-hero">
      <div className="hero-copy"><h1>您好，<br />有什么可以帮您？</h1><p>描述设备问题，让每一步售后服务都清楚、安心。</p>
        <div className="home-entry-wrap">
          <MessageComposer className="diagnosis-entry home-diagnosis-entry" desk={false} active={!busy} draft={draft}
            internal={false} onDraft={setDraft} onInternal={() => undefined} onSubmit={event => void start(event)}
            onAttach={() => void openAttachments()} draftLabel="问题描述" draftReadOnly={Boolean(pendingMessage)}
            footNote={pendingMessage ? '发送结果尚未确认；重试会使用原消息编号，避免重复发送。' : '新问题会建立独立会话；点击后直接发送这段描述。'}
            submitLabel={busy ? '正在发送…' : pendingMessage ? '用原消息重试' : '开始新的诊断'}
            footerLink={<Link className="home-history-link" to="/support"><Headphones size={18} />继续上次会话／历史问答{conversations.data ? `（${conversations.data.length}）` : ''}</Link>} />
          {error && <p className="form-error" role="alert">{error}</p>}
          {attachmentsFor && draftConversationId === attachmentsFor && <ConversationAttachments key={attachmentsFor}
            actor={actor} conversationId={attachmentsFor} customerId={actor.actor_id} initialProblem={draft || '我上传了一张图片，请帮我看看。'}
            relatedCaseIds={[]} onClose={() => setAttachmentsFor(null)} />}
        </div>
      </div>
      <p className="hero-signature">专业的支持，<br /><span>让您的使用更安心。</span></p>
    </section>
    <section className="issue-section" aria-labelledby="issues-title"><div className="panel-title"><h2 id="issues-title">常见问题类型</h2><span>选择类型，补充您的问题</span></div>
      <div className="issue-grid">{categories.map(({ title, description, icon: Icon, prompt }, index) => <button key={title} type="button" className={`issue-card tone-${index % 3}`} aria-pressed={draft.startsWith(prompt)} onClick={() => { setDraft(prompt); document.getElementById('home-problem')?.focus(); document.getElementById('home-problem')?.scrollIntoView({ block: 'center', behavior: 'smooth' }) }}><span className="round-icon"><Icon size={24} /></span><strong>{title}</strong><small>{description}</small><ChevronRight size={16} /></button>)}</div>
    </section>
    <div className="home-lower-grid"><section className="surface home-services"><div className="panel-title"><div><h2>我的服务</h2><p>随时查看服务进度，了解处理状态。</p></div><Link to="/cases">查看全部服务<ChevronRight size={15} /></Link></div>
      {cases.isPending && <p className="empty-note">正在读取服务记录…</p>}
      {cases.isError && <p role="alert" className="form-error">{readableError(cases.error)} <button onClick={() => void cases.refetch()}>重试</button></p>}
      {cases.data?.length === 0 && <div className="overview-empty"><ClipboardList size={28} /><h3>服务记录会保存在这里</h3><p>已有案例后，可查看证据、处理动作与结果核验。</p><Link to="/support">进入服务会话<ArrowRight size={15} /></Link></div>}
      <div className="service-card-grid">{cases.data?.slice(0, 2).map(item => <Link className="service-preview" key={item.id} to={`/cases/${item.id}`}><span className="object-symbol"><ClipboardList size={27} /></span><div><strong>{item.problem_text}</strong><small>提交时间　{new Date(item.created_at).toLocaleString('zh-CN')}</small><small>服务编号　{item.id.slice(0, 8)}{isDemoRecord(item.problem_text) && <span className="demo-label">演示</span>}</small></div><StatusBadge value={item.status} /><div className="saved-state"><span className="status-dot" />查看服务进展<ArrowRight size={14} /><span>问题、证据与处理记录</span></div></Link>)}</div>
    </section>
    <section className="surface home-devices"><div className="panel-title"><div><h2>我的设备</h2><p>设备档案与每一次服务记录相互关联。</p></div><Link to="/devices">管理设备<ChevronRight size={15} /></Link></div>
      {devices.isPending && <p className="empty-note">正在读取设备…</p>}
      {devices.isError && <p className="form-error" role="alert">{readableError(devices.error)} <button onClick={() => void devices.refetch()}>重试</button></p>}
      <div className="home-device-grid">{devices.data?.slice(0, 3).map(item => <Link to={`/devices/${item.id}`} key={item.id} className="device-preview"><span className="device-object"><DeviceIcon model={item.model} size={42} strokeWidth={1.4} /></span><strong>{item.model || '型号待补充'}</strong><small><StatusBadge value={item.identity_status} /></small></Link>)}</div>
      {devices.data?.length === 0 && <div className="overview-empty"><MonitorSmartphone size={28} /><p>当前还没有设备档案。</p><Link to="/support">在服务会话中补充设备信息</Link></div>}
    </section></div>
    <div className="trust-strip">{[{ icon: Sparkles, title: '智能服务会话', text: '根据实际处理结果继续沟通' }, { icon: Headphones, title: '人工协作接续', text: '在同一会话保留服务上下文' }, { icon: ClipboardList, title: '服务进展可查', text: '证据、动作与结果分别记录' }, { icon: ShieldCheck, title: '安全与隐私保障', text: '仅展示当前账号授权的记录' }].map(({ icon: Icon, title, text }) => <div key={title}><span className="round-icon"><Icon size={24} /></span><div><strong>{title}</strong><small>{text}</small></div></div>)}</div>
  </div>
}
