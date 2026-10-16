import { useQuery } from '@tanstack/react-query'
import { type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ClipboardList, ImagePlus, Lightbulb, MessagesSquare, MonitorSmartphone, UserRound, UsersRound, Zap } from 'lucide-react'
import { type Actor, type Conversation, type DeskCaseSummary, type Message, listDevices, listTasks } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { StaffCard, customerLabel } from '../../shared/StaffUI'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { StatusBadge, statusLabel } from '../../shared/StatusBadge'
import { isDemoRecord } from '../../shared/servicePresentation'
import { CollaborationPanel } from '../collaboration/CollaborationPanel'

export function StaffConversationContext({ actor, conversation, summaries, messages, summaryError, loading, interactions, onPhotoDraft }: {
  actor: Actor, conversation: Conversation, summaries: DeskCaseSummary[] | undefined,
  messages: Message[], summaryError?: string, loading: boolean, interactions: ReactNode, onPhotoDraft: () => void,
}) {
  const deviceIds = new Set(summaries?.flatMap(summary => summary.device_ids))
  const devices = useQuery({ queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices, enabled: deviceIds.size > 0 })
  const tasks = useQuery({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id), queryFn: () => listTasks(conversation.id), refetchInterval: 10_000 })
  const associated = devices.data?.filter(device => deviceIds.has(device.id))
  const assigned = tasks.data?.find(task => task.status === 'ASSIGNED')
  const lastAgent = messages.filter(message => message.author_kind === 'AGENT').at(-1)
  function openCollaboration() {
    const panel = document.querySelector<HTMLDetailsElement>('#staff-collaboration .collaboration-settings')
    if (panel) { panel.open = true; panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }
  }
  return <aside className="context-panel staff-conversation-context" aria-label="案例与协作信息">
    <StaffCard icon={UserRound} title="客户信息"><dl className="staff-compact-info"><div><dt>客户</dt><dd>{customerLabel(conversation.customer_id)}</dd></div><div><dt>会话创建</dt><dd>{new Date(conversation.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</dd></div></dl></StaffCard>
    <div id="staff-collaboration" className="staff-card staff-pending-work"><CollaborationPanel conversation={conversation} actor={actor} desk compact /></div>
    <StaffCard icon={MonitorSmartphone} title="设备信息" action={<Link to="/devices">查看设备</Link>}>
      {devices.isError && <p className="form-error">设备档案暂时无法读取。</p>}{devices.isPending && deviceIds.size > 0 && <p className="empty-note">正在查询设备…</p>}
      {associated?.map(device => <Link className="staff-context-device" to={`/devices/${device.id}`} key={device.id}><span className="staff-device-symbol"><DeviceIcon model={device.model} size={36} /></span><span><strong>{device.model || '型号待确认'}</strong><small>SN: {device.serial_number ? `••••${device.serial_number.slice(-4)}` : '未提供'}</small><StatusBadge value={device.identity_status} />{isDemoRecord(device.model) && <span className="demo-label">演示设备</span>}</span></Link>)}
      {(!deviceIds.size || !devices.isPending) && !devices.isError && !associated?.length && <p className="empty-note">{loading ? '正在确认案例关联…' : '当前会话暂无已关联的设备档案。'}</p>}
    </StaffCard>
    <StaffCard icon={UsersRound} title="当前服务状态"><dl className="staff-compact-info"><div><dt>会话状态</dt><dd><StatusBadge value={conversation.status} /></dd></div><div><dt>协作策略</dt><dd>{statusLabel(conversation.collaboration_mode)}</dd></div><div><dt>处理人</dt><dd>{assigned?.assignee_id ? assigned.assignee_id === actor.actor_id ? actor.display_name : `客服 #${assigned.assignee_id.slice(0, 8)}` : tasks.isError ? '暂时无法读取' : '暂无已接管任务'}</dd></div></dl>
      {summaryError && <p className="form-error" role="alert">{summaryError}</p>}{loading && <p className="empty-note">正在读取案例…</p>}
      {summaries?.map(summary => <div className="staff-context-case" key={summary.case.id}><Link to={`/cases/${summary.case.id}`}>{summary.case.problem_text}</Link><StatusBadge value={summary.case.status} />{summary.facts.length > 0 && <details><summary>案例事实与来源</summary><ul>{summary.facts.map((fact, index) => <li key={index}><strong>{fact.label}：</strong>{fact.value}<small>来源：{fact.source} · {statusLabel(fact.verification)}</small></li>)}</ul></details>}</div>)}
      {summaries?.length === 0 && <p className="empty-note">当前会话尚未关联案例。</p>}
    </StaffCard>
    <StaffCard icon={Lightbulb} title="AI 建议下一步" className="staff-ai-next">
      {lastAgent && <details className="staff-agent-output"><summary>最近一次助手输出</summary><p>{lastAgent.content.map(part => part.text).join('\n')}</p></details>}
      {!lastAgent && <p className="empty-note">暂无助手建议，等待实际 Agent 输出。</p>}
      <div className="staff-service-interactions">{interactions}</div>
    </StaffCard>
    <StaffCard icon={Zap} title="快捷操作"><div className="staff-quick-grid"><button type="button" disabled={conversation.status !== 'ACTIVE'} onClick={onPhotoDraft}><ImagePlus size={20} />请求补充图片</button><button type="button" onClick={openCollaboration}><MessagesSquare size={20} />人工协作与审批</button>{summaries?.map(summary => <Link key={summary.case.id} to={`/cases/${summary.case.id}`}><ClipboardList size={20} />查看关联案例</Link>)}</div></StaffCard>
  </aside>
}
