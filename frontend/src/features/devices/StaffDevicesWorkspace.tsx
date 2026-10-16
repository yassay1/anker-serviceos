import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { CheckCircle2, ChevronRight, FileText, History, MessagesSquare, Search, Settings2, ShieldCheck, MonitorSmartphone } from 'lucide-react'
import { type Actor, listDevices, readDevice, listDeviceCases, listConversations } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { CustomerAvatar, StaffCard, customerLabel } from '../../shared/StaffUI'
import { isDemoRecord, shortDate } from '../../shared/servicePresentation'
import { CaseFactPanel } from './CaseFactPanel'

const factNames: Record<string, string> = { charging_watts: '充电功率（瓦）', firmware_version: '固件版本', model: '设备型号', port_type: '接口类型' }
const factValue = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value) ?? '未提供'

export function StaffDevicesWorkspace({ actor }: { actor: Actor }) {
  const { id } = useParams()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('ALL')
  const [tab, setTab] = useState('info')
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices })
  const selectedId = id ?? devices.data?.[0]?.id
  const device = useQuery({ queryKey: queryKeys.device(actor.tenant_id, actor.actor_id, selectedId ?? ''), queryFn: () => readDevice(selectedId!), enabled: Boolean(selectedId) })
  const history = useQuery({ queryKey: queryKeys.deviceCases(actor.tenant_id, actor.actor_id, selectedId ?? ''), queryFn: () => listDeviceCases(selectedId!), enabled: Boolean(device.data) && !device.isError })
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations })
  const filtered = devices.data?.filter(item => (filter === 'ALL' || item.identity_status === filter) && `${item.model ?? ''} ${item.serial_number ?? ''} ${item.customer_id}`.toLowerCase().includes(search.trim().toLowerCase()))
  const record = !device.isError ? device.data : undefined
  const recent = conversations.data?.filter(item => item.customer_id === record?.customer_id).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  const facts = record?.verified_facts ?? []

  const historyContent = <>{history.isPending && <p className="empty-note">正在读取服务记录…</p>}{history.isError && <div className="form-error" role="alert"><p>{readableError(history.error)}</p><button onClick={() => void history.refetch()}>重新加载历史</button></div>}{history.data?.length === 0 && <p className="empty-note">暂无关联案例。</p>}
    <ol className="staff-timeline device-history">{history.data?.map(item => <li key={item.id}><span className="staff-timeline-dot"><FileText size={14} /></span><div><time dateTime={item.created_at}>{shortDate(item.created_at)}</time><Link to={`/cases/${item.id}`}><strong>{item.problem_text}</strong></Link><p><StatusBadge value={item.status} /></p><small>{item.user_goal || '未记录服务目标'}</small></div></li>)}</ol></>
  const recentContent = <>{conversations.isPending && <p className="empty-note">正在查询客户会话…</p>}{conversations.isError && <p className="form-error" role="alert">{readableError(conversations.error)}</p>}{recent?.length === 0 && <p className="empty-note">暂无已加载的客户会话。</p>}{recent?.map(item => <Link className="staff-active-conversation" key={item.id} to={`/desk?conversation=${item.id}`}><CustomerAvatar id={item.customer_id} /><span><strong>{item.title || '服务咨询'}</strong><small>{shortDate(item.created_at)} · 客户会话</small></span><ChevronRight size={16} /></Link>)}<p className="staff-data-note">以上为该客户的会话，不限于本设备。</p></>

  return <section className="staff-devices-page" aria-label="设备管理"><header className="staff-page-heading"><div><h1>设备管理</h1><p>查看设备信息、核验结果与关联服务历史，快速了解设备情况。</p></div></header>
    <div className="staff-device-layout"><aside className="staff-card staff-device-list" aria-label="设备列表"><div className="staff-card-heading"><h2>设备列表</h2><span className="muted">共 {devices.data?.length ?? '—'} 台设备</span></div>
      <label className="staff-search"><Search size={18} /><span className="visually-hidden">搜索设备</span><input placeholder="搜索设备、SN 或客户编号" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <div className="staff-filter-tabs" aria-label="设备核验状态">{[['ALL', '全部'], ['VERIFIED', '已核验'], ['UNVERIFIED', '待核验']].map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}<span>{devices.data?.filter(item => value === 'ALL' || item.identity_status === value).length ?? '—'}</span></button>)}</div>
      {devices.isPending && <p className="empty-note">正在加载设备…</p>}{devices.isError && <div className="form-error" role="alert"><p>{readableError(devices.error)}</p><button onClick={() => void devices.refetch()}>重新加载设备</button></div>}
      <ul>{filtered?.map(item => <li key={item.id}><Link to={`/devices/${item.id}`} className={selectedId === item.id ? 'selected' : ''} aria-current={selectedId === item.id ? 'page' : undefined}><span className="staff-device-symbol"><DeviceIcon model={item.model} size={35} strokeWidth={1.5} /></span><span className="device-list-copy"><strong>{item.model || '型号待确认'}</strong><small>SN: {item.serial_number ? `••••${item.serial_number.slice(-4)}` : '未提供'}</small><small>{customerLabel(item.customer_id)}</small></span><StatusBadge value={item.identity_status} /><ChevronRight size={15} /></Link></li>)}</ul>
      {devices.isSuccess && !filtered?.length && <p className="empty-note">没有符合条件的设备档案。</p>}
    </aside><div className="staff-device-detail" aria-label="当前设备档案">
      {selectedId && device.isPending && <div className="staff-card detail-placeholder">正在加载设备档案…</div>}
      {device.isError && <div className="staff-card detail-placeholder" role="alert"><h2>设备档案不可访问</h2><p>{readableError(device.error)}</p><button onClick={() => void device.refetch()}>重新检查设备</button></div>}
      {!selectedId && !devices.isPending && <div className="staff-card detail-placeholder"><MonitorSmartphone size={42} /><h2>暂无可查看的设备</h2><p>设备身份尚未确认时，也可继续服务会话。</p><Link className="button-link" to="/desk">前往客服工作区</Link></div>}
      {record && <><section className="staff-card staff-device-identity"><div className="staff-device-hero"><span className="staff-device-portrait"><DeviceIcon model={record.model} size={72} strokeWidth={1.2} /></span><div><h2>{record.model || '型号待确认'}</h2><div className="case-identity-tags"><StatusBadge value={record.identity_status} label={record.identity_status === 'VERIFIED' ? '身份已核验' : '身份待核验'} />{isDemoRecord(record.model) && <span className="demo-label">合成演示设备</span>}</div></div><div className="staff-device-hero-actions"><a className="button-link" href="#staff-device-history"><History size={16} />查看关联案例</a><button type="button" className="primary-button" onClick={() => setTab('notes')}><MessagesSquare size={16} />查看客户会话</button></div></div>
        <dl className="device-identity-strip"><div><dt>SN 编号</dt><dd>{record.serial_number ? `•••• ${record.serial_number.slice(-4)}` : '未提供'}</dd></div><div><dt>所属客户</dt><dd>{customerLabel(record.customer_id)}</dd></div></dl>
      </section>
      <div className="staff-device-body"><div className="staff-device-main"><div className="staff-detail-tabs" aria-label="设备档案内容">{[['info', '设备信息'], ['facts', '已核验事实'], ['history', '关联服务历史'], ['notes', '客户会话 / 备注']].map(([value, label]) => <button key={value} type="button" aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</div>
        {tab === 'info' && <StaffCard title="基础信息"><dl className="staff-device-fields"><div><dt>建档时间</dt><dd>{shortDate(record.created_at)}</dd></div><div><dt>已核验事实</dt><dd>{facts.length} 项</dd></div></dl><details className="staff-record-details"><summary>更多档案信息</summary><p>记录修订：{record.revision}</p><p>保修与风险信息尚未提供，可结合关联服务记录核对。</p></details></StaffCard>}
        {(tab === 'info' || tab === 'facts') && <StaffCard title="已核验事实" icon={ShieldCheck} action={<span className="status-badge success">{facts.length} 项已核验</span>}><div className="staff-verified-facts">{facts.map(fact => <article key={fact.id}><CheckCircle2 size={23} /><div><strong>{factNames[fact.fact_key] ?? fact.fact_key}</strong><p>{factValue(fact.value)}</p><details><summary>来源与核验记录</summary><p>{fact.source.startsWith('staff:') ? '客服记录' : fact.source.startsWith('customer:') ? '客户陈述' : fact.source}</p><small>核验于 {shortDate(fact.verified_at)}{fact.archived_at && ` · 归档于 ${shortDate(fact.archived_at)}`}</small>{fact.source_case_id && <Link to={`/cases/${fact.source_case_id}`}>查看来源案例</Link>}</details></div></article>)}{!facts.length && <p className="empty-note">暂无已核验事实。客户陈述和模型假设不会自动成为设备事实。</p>}</div></StaffCard>}
        {tab === 'history' && <StaffCard title="关联服务历史" icon={History}>{historyContent}</StaffCard>}
        {tab === 'notes' && <StaffCard title="客户会话与客服备注" icon={MessagesSquare}>{recentContent}<p className="staff-data-note">内部备注保存在各自会话中，请进入对应会话查看或添加。</p></StaffCard>}
        <details className="staff-advanced" key={record.id}><summary><Settings2 size={18} />设备事实管理<span>候选、核验、归档与撤销</span></summary><CaseFactPanel key={`${actor.actor_id}:${record.id}`} actor={actor} device={record} cases={history.data} /></details>
      </div><aside className="staff-device-aside">
        <div id="staff-device-history"><StaffCard title="关联服务历史" action={<button className="text-action" type="button" onClick={() => setTab('history')}>查看全部<ChevronRight size={14} /></button>}>{historyContent}</StaffCard></div><StaffCard title="该客户最近会话" action={<button className="text-action" type="button" onClick={() => setTab('notes')}>查看备注<ChevronRight size={14} /></button>}>{recentContent}</StaffCard>
      </aside></div></>}
    </div></div>
  </section>
}
