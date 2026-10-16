import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ClipboardList, Clock3, FileText, Search, ImagePlus, UserRound, MonitorSmartphone, CalendarDays } from 'lucide-react'
import type { Actor, Device, ServiceCase } from '../../api/client'
import { CaseConversationPicker } from '../../shared/CaseConversationPicker'
import { CustomerAvatar, SummaryCard, StaffCard, customerLabel } from '../../shared/StaffUI'
import { StatusBadge } from '../../shared/StatusBadge'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { caseGuidance, isDemoRecord, shortDate } from '../../shared/servicePresentation'

export function StaffCasesWorkspace({ actor, rows, loading, loaded, error, onRetry, relatedDevices }: {
  actor: Actor, rows: ServiceCase[], loading: boolean, loaded: boolean, error?: string, onRetry: () => void,
  relatedDevices: (caseId: string) => Device[],
}) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const filtered = rows.filter(row => (filter === 'all' || row.status === filter) &&
    `${row.problem_text} ${row.id} ${row.customer_id} ${relatedDevices(row.id).map(device => `${device.model} ${device.serial_number}`).join(' ')}`.toLowerCase().includes(search.trim().toLowerCase()))
  const selected = filtered.find(row => row.id === selectedId) ?? filtered[0]
  const devices = selected ? relatedDevices(selected.id) : []
  return <section className="staff-cases-page" aria-label="服务案例">
    <header className="staff-page-heading"><div><h1>服务案例</h1><p>记录每一次服务过程，沉淀经验，提升服务质量。</p></div></header>
    <div className="staff-summary-grid case-summary-grid">
      <SummaryCard icon={ClipboardList} title="待处理" value={loaded ? rows.filter(row => row.status === 'OPEN').length : '—'} tone="orange" />
      <SummaryCard icon={Clock3} title="处理中" value={loaded ? rows.filter(row => row.status === 'IN_PROGRESS').length : '—'} tone="orange" />
      <SummaryCard icon={CheckCircle2} title="已解决" value={loaded ? rows.filter(row => row.status === 'RESOLVED').length : '—'} tone="green" />
      <SummaryCard icon={ImagePlus} title="待客户补充" value={loaded ? rows.filter(row => row.status === 'WAITING_CUSTOMER').length : '—'} tone="blue" />
    </div>
    <div className="staff-cases-columns">
      <section className="staff-card staff-cases-list" aria-label="工单列表"><div className="staff-case-toolbar"><h2>案例列表</h2><label className="staff-search"><Search size={17} /><span className="visually-hidden">搜索服务记录</span><input type="search" placeholder="搜索案例、客户或设备编号" value={search} onChange={event => setSearch(event.target.value)} /></label><label className="staff-select"><span>当前阶段</span><select aria-label="筛选案例状态" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">全部</option><option value="OPEN">待处理</option><option value="IN_PROGRESS">处理中</option><option value="WAITING_CUSTOMER">待客户补充</option><option value="WAITING_EXTERNAL">待外部处理</option><option value="RESOLVED">已解决</option><option value="CLOSED">已关闭</option></select></label></div>
        {loading && <p className="empty-note" role="status">正在读取服务记录…</p>}
        {error && <div className="form-error" role="alert"><p>{error}</p><button onClick={onRetry}>重新加载服务</button></div>}
        <div className="table-scroll"><table className="staff-table staff-case-table"><thead><tr><th>案例标题</th><th>客户</th><th>关联设备</th><th>当前阶段</th><th>创建时间</th><th>操作</th></tr></thead><tbody>{filtered.map(row => <tr key={row.id} className={selected?.id === row.id ? 'is-selected' : ''}>
          <td><button type="button" className="table-title-button" aria-pressed={selected?.id === row.id} onClick={() => setSelectedId(row.id)}><strong title={row.problem_text}>{row.problem_text}</strong><small>#{row.id.slice(0, 8)}{isDemoRecord(row.problem_text) && <span className="demo-label">演示</span>}</small></button></td>
          <td><div className="table-customer"><CustomerAvatar id={row.customer_id} /><span>{customerLabel(row.customer_id)}</span></div></td>
          <td>{relatedDevices(row.id).length ? relatedDevices(row.id).map(device => <Link className="table-device" key={device.id} to={`/devices/${device.id}`}><span className="staff-device-symbol"><DeviceIcon model={device.model} size={28} /></span><span>{device.model || '型号待确认'}<small>{device.serial_number ? `SN: ••••${device.serial_number.slice(-4)}` : '序列号未提供'}</small></span></Link>) : <span className="muted">暂无关联设备</span>}</td>
          <td><StatusBadge value={row.status} /></td><td><time dateTime={row.created_at}>{shortDate(row.created_at)}</time></td><td><Link className="button-link outlined-action" to={`/cases/${row.id}`}>查看详情</Link></td>
        </tr>)}</tbody></table></div>
        {loaded && !filtered.length && <div className="detail-placeholder"><ClipboardList size={35} /><h3>没有匹配的服务案例</h3><p>调整搜索内容或切换当前阶段。</p></div>}
        <p className="staff-table-note">共 {filtered.length} 条已加载记录</p>
      </section>
      <aside className="staff-case-preview" aria-label="工单预览">{selected ? <>
        <StaffCard title="案例概览" action={<StatusBadge value={selected.status} />}><h3 className="case-preview-title">{selected.problem_text}</h3><p className="case-preview-number">#{selected.id.slice(0, 8)}{isDemoRecord(selected.problem_text) && <span className="demo-label">演示记录</span>}</p>
          <dl className="staff-info-list"><div><dt><UserRound size={17} />客户</dt><dd>{customerLabel(selected.customer_id)}</dd></div><div><dt><MonitorSmartphone size={17} />关联设备</dt><dd>{devices.length ? devices.map(device => <Link key={device.id} to={`/devices/${device.id}`}>{device.model || '型号待确认'}</Link>) : '暂无关联设备'}</dd></div><div><dt><CalendarDays size={17} />创建时间</dt><dd>{new Date(selected.created_at).toLocaleString('zh-CN')}</dd></div><div><dt><FileText size={17} />服务目标</dt><dd>{selected.user_goal || '尚未补充'}</dd></div></dl>
        </StaffCard>
        <StaffCard title="当前待办"><div className="staff-preview-content"><h3>{caseGuidance(selected.status, true).title}</h3><p>{caseGuidance(selected.status, true).body}</p></div><div className="staff-preview-actions"><CaseConversationPicker key={selected.id} actor={actor} serviceCase={selected} /><Link className="button-link" to={`/cases/${selected.id}`}><FileText size={18} />完整记录</Link></div></StaffCard>
      </> : <StaffCard title="案例概览"><div className="detail-placeholder"><ClipboardList size={32} /><p>选择一个案例，查看客户、设备和处理进度。</p></div></StaffCard>}</aside>
    </div>
  </section>
}
