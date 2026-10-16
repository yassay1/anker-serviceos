import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, FileText } from 'lucide-react'
import { type Actor, readCase } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'
import { type AgentProgress, type SpecialistActivity } from './useConversationEvents'

const progressLabels: Record<AgentProgress['stage'], string> = {
  RUNNING: '正在处理', LOOKUP: '正在查阅资料', WAITING_EVIDENCE: '等待补充信息',
  WAITING_APPROVAL: '等待审批', COMPLETED: '本轮处理结束', FAILED: '本轮处理失败',
}

export function AgentProgressNote({ progress, connected }: { progress: AgentProgress, connected: boolean }) {
  return <section className={`agent-progress stage-${progress.stage}`} aria-label="助手最新进度" aria-live="polite">
    <div><Activity size={16} aria-hidden="true" /><strong>{progressLabels[progress.stage]}</strong>{!connected && <small>上次收到的进度</small>}</div>
    <p>{progress.summary}</p>
    {progress.stage === 'COMPLETED' && <small>本轮运行结束不代表问题已解决，服务结果以案例核验为准。</small>}
  </section>
}

const specialistStageLabels: Record<SpecialistActivity['stage'], string> = {
  STARTED: '开始分析', LOOKUP: '查阅授权资料', RESULT_READY: '形成待核验假设',
  WAITING_CUSTOMER: '等待你的补充信息', WAITING_STAFF: '等待客服进一步核实', FAILED: '本次分析未完成',
}

export function SpecialistActivityNote({ activity, connected }: { activity: SpecialistActivity, connected: boolean }) {
  return <section className={`agent-progress specialist-activity stage-${activity.stage}`} aria-label="诊断专家活动" aria-live="polite">
    <div><Activity size={16} aria-hidden="true" /><strong>{activity.displayName} · {specialistStageLabels[activity.stage]}</strong>{!connected && <small>上次收到的专家活动</small>}</div>
    <p>{activity.summary}</p>
    {activity.certainty === 'HYPOTHESIS' && <small>这是待核验的诊断假设，不是已确认的设备事实。</small>}
  </section>
}

function RelatedCase({ actor, id }: { actor: Actor, id: string }) {
  const query = useQuery({ queryKey: queryKeys.case(actor.tenant_id, actor.actor_id, id), queryFn: () => readCase(id), refetchInterval: 10_000 })
  if (query.isPending) return <p>正在加载关联案例…</p>
  if (query.isError) return <div className="related-case-error"><p className="form-error" role="alert">{readableError(query.error)}</p><button type="button" onClick={() => void query.refetch()}>重试案例</button></div>
  const item = query.data
  return <article>
    <h4><Link to={`/cases/${id}`}>{item.problem_text}</Link></h4>
    <p><StatusBadge value={item.status} /> <span>版本 {item.version}</span></p>
    <details className="case-disclosure"><summary>服务目标与下一步</summary>
      <p>{item.user_goal || '尚未记录服务目标。'}</p>
      <p>{item.status === 'WAITING_CUSTOMER' ? '查看案例中需要补充的证据或结果核验，再按实际情况反馈。' :
        item.status === 'WAITING_EXTERNAL' ? '正在等待外部处理；请在案例页查看实际回执。' :
          ['RESOLVED', 'CLOSED'].includes(item.status) ? '可在案例页查看处理与核验记录。' : '可在案例页补充图片、查看处理记录与核验要求。'}</p>
    </details>
    <Link className="related-case-link" to={`/cases/${id}`}>证据与处理记录 <ArrowUpRight size={14} aria-hidden="true" /></Link>
  </article>
}

export function RelatedCases({ actor, ids }: { actor: Actor, ids: string[] }) {
  return <section className="case-summary" aria-label="关联服务案例">
    <div className="context-heading"><h3><FileText size={17} aria-hidden="true" />关联服务案例</h3></div>
    {ids.length ? <><p>来自当前会话消息中的案例关联。</p>{ids.map(id => <RelatedCase key={id} actor={actor} id={id} />)}</> :
      <p>当前已加载的消息尚无案例关联。可以继续描述问题，不必先创建或选择设备。</p>}
    <details className="case-disclosure"><summary>更多服务资料</summary><p>案例记录一次问题，设备档案记录长期已核验信息；两者独立保存。</p>
      <div className="device-references"><Link to="/cases">查看我的服务案例</Link><Link to="/devices">查看设备档案</Link></div>
    </details>
  </section>
}
