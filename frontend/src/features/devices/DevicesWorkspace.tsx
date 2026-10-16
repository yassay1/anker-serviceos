import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { CheckCircle2, Clock3, ShieldCheck } from 'lucide-react'
import { type Actor, listDevices, readDevice, listDeviceCases } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { isDemoRecord } from '../../shared/servicePresentation'
import { CaseFactPanel } from './CaseFactPanel'
import { StaffDevicesWorkspace } from './StaffDevicesWorkspace'

const date = (value: string) => new Date(value).toLocaleDateString('zh-CN')
const factValue = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value) ?? '未提供'
const sourceLabel = (value: string) => value.startsWith('staff:') ? '客服记录'
  : value.startsWith('customer:') ? '客户陈述' : value
// Unknown keys retain their original names; do not infer a diagnosis or unit.
const factNames: Record<string, string> = { charging_watts: '充电功率（瓦）', firmware_version: '固件版本', model: '设备型号', port_type: '接口类型' }

export function DevicesWorkspace({ actor }: { actor: Actor }) {
  return actor.kind === 'STAFF' ? <StaffDevicesWorkspace actor={actor} /> : <CustomerDevicesWorkspace actor={actor} />
}

function CustomerDevicesWorkspace({ actor }: { actor: Actor }) {
  const { id } = useParams()
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices })
  const selectedId = id ?? devices.data?.[0]?.id
  const device = useQuery({ queryKey: queryKeys.device(actor.tenant_id, actor.actor_id, selectedId ?? ''),
    queryFn: () => readDevice(selectedId!), enabled: Boolean(selectedId) })
  const history = useQuery({ queryKey: queryKeys.deviceCases(actor.tenant_id, actor.actor_id, selectedId ?? ''),
    queryFn: () => listDeviceCases(selectedId!), enabled: Boolean(device.data) && !device.isError })
  return <div className="devices-page">
    <div className="page-heading"><div><h1>我的设备</h1><p>设备身份、已核验事实与持续服务记录。</p></div><span className="scope-note"><ShieldCheck size={15} aria-hidden="true" />当前账号授权范围</span></div>
    <div className="device-layout">
      <aside className="device-list" aria-label="设备列表"><div className="section-heading"><h2>{actor.kind === 'STAFF' ? '可查看的设备' : '设备档案'}</h2><span className="device-count">{devices.data?.length ?? '—'}</span></div>
        {devices.isPending && <p className="muted">正在加载设备…</p>}
        {devices.isError && <div className="form-error" role="alert"><p>{readableError(devices.error)}</p><button onClick={() => void devices.refetch()}>重新加载设备</button></div>}
        {devices.data?.length === 0 && <p className="muted">暂无设备档案；仍可在用户服务中描述问题。</p>}
        <ul>{devices.data?.map(item => <li key={item.id}><Link to={`/devices/${item.id}`} className={selectedId === item.id ? 'selected' : ''} aria-current={selectedId === item.id ? 'page' : undefined}>
          <span className="device-thumbnail"><DeviceIcon model={item.model} size={25} /></span><span><strong>{item.model ?? '型号待确认'}</strong><small>{item.identity_status === 'VERIFIED' ? '身份已核验' : '身份待核验'} · #{item.id.slice(0, 8)}</small></span>
        </Link></li>)}</ul>
      </aside>
      <section className="device-detail" aria-label="当前设备档案">
        {selectedId && device.isPending && <div className="detail-placeholder">正在加载设备档案…</div>}
        {device.isError && <div className="detail-placeholder" role="alert"><h2>设备档案不可访问</h2><p>{readableError(device.error)}</p><button onClick={() => void device.refetch()}>重新检查设备</button></div>}
        {!selectedId && !devices.isPending && <div className="detail-placeholder"><DeviceIcon size={40} /><h2>服务可以先从问题开始</h2><p>设备身份尚未确认时，也可以建立会话。</p><Link className="button-link" to={actor.kind === 'STAFF' ? '/desk' : '/support'}>前往{actor.kind === 'STAFF' ? '客服工作区' : '用户服务'}</Link></div>}
        {device.data && !device.isError && <>
          <div className="device-hero"><span className="device-illustration"><DeviceIcon model={device.data.model} size={56} strokeWidth={1.4} /></span>
            <div><div className="case-identity-tags"><StatusBadge value={device.data.identity_status} label={device.data.identity_status === 'VERIFIED' ? '身份已核验' : '身份待核验'} />{isDemoRecord(device.data.model) && <span className="demo-label">合成演示设备</span>}</div><h2>{device.data.model ?? '型号待确认'}</h2><p>设备标识：{device.data.serial_number ? `•••• ${device.data.serial_number.slice(-4)}` : '未提供'}</p><p className="muted">建立于 {date(device.data.created_at)} · 档案修订 {device.data.revision}</p></div></div>
          <div className="device-confidence"><ShieldCheck size={19} aria-hidden="true" /><p><strong>设备身份与事实分别核验</strong><span>以下事实保留来源记录；身份待核验不代表已核验事实失效。</span></p></div>
          <div className="device-sections"><section aria-label="已核验事实"><h3><CheckCircle2 size={18} aria-hidden="true" />已核验事实</h3><p className="muted">保留信息来源和核验时间，方便回看与核对。</p>
            {device.data.verified_facts?.length ? <dl className="fact-list">{device.data.verified_facts.map(fact => <div key={fact.id}><dt>{factNames[fact.fact_key] ?? fact.fact_key}</dt><dd>{factValue(fact.value)}<small>来源：{fact.source_case_id ? `案例 #${fact.source_case_id.slice(0, 8)} · ` : ''}{sourceLabel(fact.source)} · 客服核验于 {date(fact.verified_at)}{fact.archived_at ? ` · 归档于 ${date(fact.archived_at)}` : ''}</small></dd></div>)}</dl> : <p className="empty-note">暂无已核验事实。客户陈述和模型假设不会自动成为设备事实。</p>}
          </section><section aria-label="设备服务历史"><h3><Clock3 size={18} aria-hidden="true" />服务历史</h3>
            {history.isPending && <p className="muted">正在读取服务记录…</p>}
            {history.isError && <div role="alert" className="form-error"><p>{readableError(history.error)}</p><button onClick={() => void history.refetch()}>重新加载历史</button></div>}
            {history.data?.length === 0 && <p className="empty-note">暂无关联案例。设备档案和服务案例独立保存。</p>}
            <ol className="history-list">{history.data?.map(item => <li key={item.id}><time dateTime={item.created_at}>{date(item.created_at)}</time><div><h4><Link to={`/cases/${item.id}`}>{item.problem_text}</Link></h4><StatusBadge value={item.status} />{item.user_goal && <p>期望结果：{item.user_goal}</p>}<Link className="history-case-link" to={`/cases/${item.id}`}>查看服务记录 <span aria-hidden="true">↗</span></Link><small>案例 #{item.id.slice(0, 8)} · 版本 {item.version}</small></div></li>)}</ol>
          </section></div>
          {actor.kind === 'STAFF' && <CaseFactPanel key={`${actor.actor_id}:${device.data.id}`} actor={actor}
            device={device.data} cases={history.data} />}
        </>}
      </section>
    </div>
  </div>
}
