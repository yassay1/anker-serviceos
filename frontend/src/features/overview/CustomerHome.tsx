import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, ChevronRight, Power, Wifi, Box, Wrench, Truck, ClipboardList, Sparkles, Headphones, ShieldCheck, MonitorSmartphone, ImagePlus, X } from 'lucide-react'
import { type Actor, createConversation, listCases, listDevices, listConversations, sendMessage } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { StatusBadge } from '../../shared/StatusBadge'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { isDemoRecord } from '../../shared/servicePresentation'
import { readableError } from '../../shared/errors'

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
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases })
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices })
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations })

  const allowed = ['image/jpeg', 'image/png', 'image/webp']
  function addFiles(list: FileList | null) {
    setFileError('')
    if (!list) return
    const next = [...files]
    for (const file of Array.from(list)) {
      if (!allowed.includes(file.type) || file.size === 0 || file.size > 10 * 1024 * 1024) {
        setFileError('仅支持不超过 10 MiB 的 JPEG、PNG 或 WebP 图片。')
        continue
      }
      if (next.length >= 5) { setFileError('一次最多携带 5 张图片。'); break }
      next.push(file)
    }
    setFiles(next)
    if (fileInput.current) fileInput.current.value = ''
  }

  async function start(event: FormEvent) {
    event.preventDefault()
    if (busy || !draft.trim()) return
    setBusy(true); setError('')
    try {
      const conversation = await createConversation()
      await queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      let sent = true
      try {
        await sendMessage(conversation.id, { client_message_id: crypto.randomUUID(),
          content: [{ type: 'text', text: draft.trim() }], visibility: 'PUBLIC' })
      } catch {
        sent = false
      }
      navigate(`/support?conversation=${conversation.id}`, {
        state: sent ? { autoAttachFiles: files.length ? files : undefined }
          : { draft: draft.trim(), autoAttachFiles: files.length ? files : undefined },
      })
    } catch (failure) { setError(readableError(failure)); setBusy(false) }
  }

  return <div className="customer-home">
    <section className="home-hero">
      <div className="hero-copy"><h1>您好，<br />有什么可以帮您？</h1><p>描述设备问题，让每一步售后服务都清楚、安心。</p>
        <form className="diagnosis-entry" onSubmit={event => void start(event)}>
          <label className="visually-hidden" htmlFor="home-problem">问题描述</label>
          <textarea id="home-problem" placeholder="请描述您遇到的问题，例如：设备无法开机、出现故障代码、噪音异常等…" value={draft} onChange={event => setDraft(event.target.value)} maxLength={8000} required aria-describedby="home-entry-hint" />
          <div className="home-attach-row">
            <button type="button" className="ghost-button" onClick={() => fileInput.current?.click()} aria-label="添加图片">
              <ImagePlus size={18} />添加图片
            </button>
            <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
              onChange={event => addFiles(event.target.files)} />
            {files.map((file, index) => <span key={`${file.name}:${index}`} className="attach-chip">
              {file.name}
              <button type="button" aria-label={`移除 ${file.name}`}
                onClick={() => setFiles(files.filter((_, i) => i !== index))}><X size={14} /></button>
            </span>)}
          </div>
          {fileError && <p className="form-error" role="alert">{fileError}</p>}
          <p id="home-entry-hint" className="entry-hint">点击后将开启独立会话并立即发送；图片进入会话后自动归入服务案例证据。</p>
          <div className="diagnosis-entry-foot"><Link to="/support"><Headphones size={18} />继续上次会话／历史问答{conversations.data ? `（${conversations.data.length}）` : ''}</Link><button className="primary-button" type="submit" disabled={busy}><Sparkles size={19} />{busy ? '正在发送…' : '开始新的诊断'}<ArrowRight size={19} /></button></div>
          {error && <p className="form-error" role="alert">{error}</p>}
        </form>
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
