import { useQueries, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ClipboardList, MessagesSquare, Search, CheckCircle2, ImagePlus, Settings2, ChevronRight } from 'lucide-react'
import { type Actor, listCases, listConversations, listDevices, listDeviceCases } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
import { CustomerAvatar, SummaryCard, StaffCard, customerLabel } from '../../shared/StaffUI'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { isDemoRecord } from '../../shared/servicePresentation'
import { KnowledgePanel } from './KnowledgePanel'
import { GuardPanel } from './GuardPanel'

export function DeskOverview({ actor }: { actor: Actor }) {
  const [filter, setFilter] = useState('open')
  const [search, setSearch] = useState('')
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases, refetchInterval: 10_000 })
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations, refetchInterval: 10_000 })
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices })
  const histories = useQueries({ queries: (devices.data ?? []).map(device => ({
    queryKey: queryKeys.deviceCases(actor.tenant_id, actor.actor_id, device.id), queryFn: () => listDeviceCases(device.id),
  })) })
  const rows = cases.data ?? []
  const open = rows.filter(item => !['RESOLVED', 'CLOSED'].includes(item.status))
  const waiting = rows.filter(item => item.status === 'WAITING_CUSTOMER')
  const active = conversations.data?.filter(item => item.status === 'ACTIVE')
  const visible = rows.filter(item => (filter === 'all' || (filter === 'waiting' ? item.status === 'WAITING_CUSTOMER' : filter === 'resolved' ? item.status === 'RESOLVED' : !['RESOLVED', 'CLOSED'].includes(item.status))) && `${item.problem_text} ${item.id} ${item.customer_id}`.toLowerCase().includes(search.trim().toLowerCase())).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || a.id.localeCompare(b.id))
  return <div className="desk-overview staff-overview">
    <header className="staff-page-heading"><div><h1>你好，{actor.display_name}</h1><p>今天是 {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}。专注处理客户问题，让每一次服务有回应。</p></div></header>
    <div className="staff-summary-grid">
      <SummaryCard icon={MessagesSquare} title="活跃会话" value={conversations.isSuccess ? active?.length : '—'} note="当前加载的活跃会话" />
      <SummaryCard icon={CheckCircle2} title="已解决案例" value={cases.isSuccess ? rows.filter(item => item.status === 'RESOLVED').length : '—'} note="当前加载的已解决案例" tone="green" />
      <SummaryCard icon={ClipboardList} title="待跟进案例" value={cases.isSuccess ? open.length : '—'} note="尚未解决或关闭的案例" tone="orange" />
      <SummaryCard icon={ImagePlus} title="待客户补充" value={cases.isSuccess ? waiting.length : '—'} note="等待客户提供进一步信息" tone="orange" />
    </div>
    <div className="staff-overview-columns">
      <section className="staff-card staff-queue"><div className="queue-heading"><div><h2>服务处理队列</h2><p>按创建时间从新到旧，查看服务事项。</p></div><label className="staff-search"><Search size={17} /><span className="visually-hidden">搜索已加载案例</span><input placeholder="搜索客户、问题或案例" value={search} onChange={event => setSearch(event.target.value)} /></label></div>
        <div className="staff-filter-tabs" aria-label="案例状态">{[['open', '待跟进', open.length], ['waiting', '待客户补充', waiting.length], ['resolved', '已解决', rows.filter(item => item.status === 'RESOLVED').length], ['all', '全部', rows.length]].map(([value, label, count]) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(String(value))}>{label}<span>{cases.isSuccess ? count : '—'}</span></button>)}</div>
        {cases.isPending && <p className="empty-note">正在读取案例…</p>}
        {cases.isError && <p className="form-error" role="alert">{readableError(cases.error)} <button onClick={() => void cases.refetch()}>重试</button></p>}
        <div className="table-scroll"><table className="staff-table queue-table"><thead><tr><th>客户与问题</th><th>设备</th><th>创建时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{visible.map(item => {
          const device = devices.data?.find((_, index) => histories[index]?.data?.some(record => record.id === item.id))
          return <tr key={item.id}><td><div className="queue-customer"><CustomerAvatar id={item.customer_id} /><div><strong>{customerLabel(item.customer_id)}</strong><p title={item.problem_text}><Link to={`/cases/${item.id}`}>{item.problem_text}</Link></p><small>#{item.id.slice(0, 8)}{isDemoRecord(item.problem_text) && <span className="demo-label">演示</span>}</small></div></div></td>
            <td><div className="queue-device"><span className="staff-device-symbol"><DeviceIcon model={device?.model} size={27} /></span><span>{device?.model || (histories.some(query => query.isPending) ? '正在查询…' : '暂无关联设备')}<small>{device?.serial_number ? `SN: ••••${device.serial_number.slice(-4)}` : '设备身份以档案为准'}</small></span></div></td>
            <td><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}<small>{new Date(item.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</small></time></td>
            <td><StatusBadge value={item.status} /></td><td><Link className="button-link primary-button" to={`/cases/${item.id}`}>查看案例</Link></td></tr>
        })}</tbody></table></div>
        {cases.isSuccess && visible.length === 0 && <div className="detail-placeholder"><ClipboardList size={34} /><h3>没有符合条件的案例</h3><p>切换状态或调整关键词查看服务记录。</p></div>}
        <p className="staff-table-note">已加载 {rows.length} 条案例，统计仅覆盖当前接口返回的记录。</p>
      </section>
      <aside className="staff-overview-aside">
        <StaffCard title="今日关注"><button type="button" className="attention-row" onClick={() => setFilter('waiting')}><span className="attention-icon tone-orange"><ImagePlus size={21} /></span><span><strong>等待客户补充</strong><small>查看案例中的补充资料要求</small></span><b>{cases.isSuccess ? waiting.length : '—'}</b><ChevronRight size={16} /></button>
          <button type="button" className="attention-row" onClick={() => setFilter('open')}><span className="attention-icon tone-blue"><ClipboardList size={21} /></span><span><strong>待跟进案例</strong><small>继续尚未结束的服务</small></span><b>{cases.isSuccess ? open.length : '—'}</b><ChevronRight size={16} /></button>
          <Link className="attention-row" to="/desk"><span className="attention-icon tone-green"><MessagesSquare size={21} /></span><span><strong>活跃会话</strong><small>与客户继续沟通</small></span><b>{conversations.isSuccess ? active?.length : '—'}</b><ChevronRight size={16} /></Link>
          <Link className="button-link primary-button full-width" to="/desk"><MessagesSquare size={18} />前往服务会话</Link>
        </StaffCard>
        <StaffCard title="当前活跃会话" action={<Link to="/desk">查看全部<ChevronRight size={14} /></Link>}>
          {conversations.isPending && <p className="empty-note">正在读取会话…</p>}
          {conversations.isError && <p className="form-error" role="alert">{readableError(conversations.error)}<button onClick={() => void conversations.refetch()}>重试</button></p>}
          {active?.slice(0, 3).map(item => <Link className="staff-active-conversation" key={item.id} to={`/desk?conversation=${item.id}`}><CustomerAvatar id={item.customer_id} /><span><strong>{customerLabel(item.customer_id)}</strong><small>{item.title || '服务咨询'}</small></span><ArrowRight size={16} /></Link>)}
          {active?.length === 0 && <p className="empty-note">暂无活跃会话。</p>}
        </StaffCard>
      </aside>
    </div>
    <details className="staff-advanced"><summary><Settings2 size={18} />高级工作区<span>知识文档与发布审查</span></summary><KnowledgePanel actor={actor} /><GuardPanel actor={actor} /></details>
  </div>
}
