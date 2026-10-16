import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ClipboardList, MessagesSquare, MonitorSmartphone, Search, Sparkles, CheckCircle2, ShieldCheck } from 'lucide-react'
import { type Actor, listCases, listConversations, listDevices } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
import { KnowledgePanel } from './KnowledgePanel'

export function DeskOverview({ actor }: { actor: Actor }) {
  const [filter, setFilter] = useState('open')
  const [search, setSearch] = useState('')
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases, refetchInterval: 10_000 })
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations, refetchInterval: 10_000 })
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices, refetchInterval: 10_000 })
  const open = cases.data?.filter(item => !['RESOLVED', 'CLOSED'].includes(item.status))
  const resolved = cases.data?.filter(item => item.status === 'RESOLVED')
  const active = conversations.data?.filter(item => item.status === 'ACTIVE')
  const visible = cases.data?.filter(item => (filter === 'all' || (filter === 'resolved' ? item.status === 'RESOLVED' : !['RESOLVED', 'CLOSED'].includes(item.status))) && `${item.problem_text} ${item.id} ${item.customer_id}`.toLowerCase().includes(search.trim().toLowerCase()))
  return <div className="desk-overview">
    <section className="desk-welcome"><h1>你好，{actor.display_name}！</h1><p>今天是 {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}。从当前授权的服务记录开始。</p><span className="desk-welcome-note">专业的支持，让服务更安心。</span></section>
    <div className="metric-grid">{[
      { icon: ClipboardList, title: '待继续处理案例', value: cases.isError ? '—' : open?.length, note: '当前加载案例中的未结束记录', tone: 'peach' },
      { icon: CheckCircle2, title: '已解决案例', value: cases.isError ? '—' : resolved?.length, note: '以服务器 RESOLVED 状态为准', tone: 'green' },
      { icon: MessagesSquare, title: '活跃服务会话', value: conversations.isError ? '—' : active?.length, note: '当前加载的 ACTIVE 会话', tone: 'blue' },
      { icon: MonitorSmartphone, title: '授权设备档案', value: devices.isError ? '—' : devices.data?.length, note: '当前加载的可见设备记录', tone: 'peach' },
    ].map(({ icon: Icon, title, value, note, tone }) => <section className="metric-card" key={title}><span className={`round-icon ${tone}`}><Icon size={24} /></span><div><h2>{title}</h2><strong>{value ?? '…'}</strong><p>{note}</p></div></section>)}</div>
    <div className="overview-columns"><section className="surface case-table-panel"><div className="overview-tabs" aria-label="案例状态">{[['open', '待继续处理'], ['resolved', '已解决'], ['all', '全部案例']].map(([value, title]) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{title}</button>)}</div>
      <div className="table-toolbar"><span>服务案例</span><label className="search-field"><Search size={17} /><span className="visually-hidden">搜索已加载案例</span><input placeholder="搜索案例编号、问题或客户" value={search} onChange={event => setSearch(event.target.value)} /></label></div>
      {cases.isPending && <p className="empty-note">正在读取案例…</p>}
      {cases.isError && <p className="form-error" role="alert">{readableError(cases.error)} <button onClick={() => void cases.refetch()}>重试</button></p>}
      <div className="table-scroll"><table className="case-table"><thead><tr><th>案例信息</th><th>当前状态</th><th>创建时间</th><th><span className="visually-hidden">操作</span></th></tr></thead><tbody>{visible?.map(item => <tr key={item.id}><td><Link to={`/cases/${item.id}`}>{item.problem_text}</Link><small>#{item.id.slice(0, 8)}　·　客户 {item.customer_id.slice(0, 8)}</small></td><td><StatusBadge value={item.status} /></td><td><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</time></td><td><Link to={`/cases/${item.id}`} aria-label={`查看案例 ${item.id.slice(0, 8)}`}><ArrowRight size={17} /></Link></td></tr>)}</tbody></table></div>
      {!cases.isPending && !cases.isError && visible?.length === 0 && <div className="overview-empty"><ClipboardList size={30} /><h3>没有符合条件的案例</h3><p>可切换状态或调整搜索内容。</p></div>}
      <p className="table-foot">已加载 {cases.data?.length ?? 0} 条案例 · 列表接口最多返回 50 条，以上数量为当前记录统计</p>
    </section><aside className="surface overview-assistant"><h2><span className="round-icon"><Sparkles size={21} /></span>服务协作助手</h2><h3>把服务的下一步，<br />放在同一个工作现场。</h3><p>打开客户会话，查看关联案例、补充信息、审阅草稿，并由授权客服决定公开回复。</p>
      <div className="assistant-shortcuts"><Link to="/desk"><MessagesSquare size={21} /><strong>沟通与接管</strong><small>继续真实客户会话</small></Link><Link to="/cases"><ClipboardList size={21} /><strong>案例与证据</strong><small>查看保存的服务进展</small></Link><Link to="/devices"><MonitorSmartphone size={21} /><strong>设备档案</strong><small>查询身份与已核验事实</small></Link><Link to="/desk"><ShieldCheck size={21} /><strong>人工审阅</strong><small>在会话中核对待审内容</small></Link></div>
      <h4>当前活跃会话</h4>{conversations.isError && <p className="form-error" role="alert">{readableError(conversations.error)} <button onClick={() => void conversations.refetch()}>重试</button></p>}
      {active?.slice(0, 3).map(item => <Link className="active-conversation" key={item.id} to={`/desk?conversation=${item.id}`}><span className="account-avatar">客</span><span><strong>客户 {item.customer_id.slice(0, 8)}</strong><small>会话 #{item.id.slice(0, 8)}</small></span><ArrowRight size={16} /></Link>)}
      {active?.length === 0 && <p className="empty-note">暂无已加载的活跃会话。</p>}
      {devices.isError && <p className="form-error" role="alert">设备档案：{readableError(devices.error)} <button onClick={() => void devices.refetch()}>重试</button></p>}
      <div className="assistant-note"><ShieldCheck size={18} /><p>诊断与建议以实际会话记录为准，内部草稿经审阅后才能公开。</p></div>
    </aside></div>
    <KnowledgePanel actor={actor} />
  </div>
}
