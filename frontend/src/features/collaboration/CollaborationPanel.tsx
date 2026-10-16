import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiFailure, type Actor, type Conversation, claimTask, decideProposal, listProposals, listTasks, transitionMode } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { UsersRound } from 'lucide-react'
import { statusLabel } from '../../shared/StatusBadge'

export function CollaborationPanel({ conversation, actor, desk, compact = false }: { conversation: Conversation, actor: Actor, desk: boolean, compact?: boolean }) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('需要人工协助处理当前问题')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const active = conversation.status === 'ACTIVE'
  const [mode, setMode] = useState<'AI_LEAD' | 'CO_SERVICE' | 'HUMAN_LEAD'>(conversation.collaboration_mode as 'AI_LEAD' | 'CO_SERVICE' | 'HUMAN_LEAD')
  useEffect(() => setMode(conversation.collaboration_mode as typeof mode), [conversation.collaboration_mode, conversation.version])
  const tasks = useQuery({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id), queryFn: () => listTasks(conversation.id), enabled: desk, refetchInterval: 10_000 })
  const proposals = useQuery({ queryKey: queryKeys.proposals(actor.tenant_id, conversation.id), queryFn: () => listProposals(conversation.id), enabled: desk, refetchInterval: 10_000 })

  async function refreshState() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.proposals(actor.tenant_id, conversation.id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, conversation.id) }),
    ])
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      await refreshState()
    } catch (failure) {
      setError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status === 409) {
        await refreshState()
      }
    } finally {
      setBusy(false)
    }
  }

  const taskRows = (tasks.data ?? []).map(task => <div className="collaboration-item" key={task.id}>
    <span>{task.reason} · {statusLabel(task.status)} · 版本 {task.version}</span>
    {task.status === 'OPEN' && <button type="button" disabled={busy || !active} onClick={() => void run(() => claimTask(task.id, task.version))}>接管</button>}
  </div>)
  const proposalRows = (proposals.data ?? []).map(proposal => <div className="collaboration-item" key={proposal.id}>
    <span>{proposal.proposal_type === 'REPLY' ? '回复草稿' : proposal.proposal_type} · {String(proposal.payload.summary ?? '')} · {statusLabel(proposal.status)}</span>
    {proposal.status === 'DRAFT' && <span className="proposal-actions"><button type="button" disabled={busy || !active || reason.trim().length < 3} onClick={() => void run(() => decideProposal(proposal.id, 'APPROVED', reason.trim(), crypto.randomUUID()))}>批准</button>{' '}<button type="button" disabled={busy || !active || reason.trim().length < 3} onClick={() => void run(() => decideProposal(proposal.id, 'REJECTED', reason.trim(), crypto.randomUUID()))}>拒绝</button></span>}
  </div>)
  return <section className="collaboration-panel" aria-label="人机协作">
    <h3><UsersRound size={18} aria-hidden="true" />{desk ? compact ? '待接管与回复审批' : '人机协作' : '需要真人一起处理？'}</h3>
    {!compact && <p className="policy-summary">当前：{statusLabel(conversation.collaboration_mode)} · 发言策略：{statusLabel(conversation.reply_policy)} · 版本 {conversation.version}</p>}
    {!active && <p className="form-hint">此会话已归档，协作操作已停止。</p>}
    {!desk && <p>已有会话会继续保留。请在下方服务交互卡提交人工协助请求；卡片暂不可用时，可在文字消息中说明需求。</p>}
    {desk && <>
      <label className="collaboration-reason">原因 <input value={reason} disabled={busy || !active} onChange={(event) => setReason(event.target.value)} minLength={3} maxLength={1000} /></label>
      {compact && <><h4>人工任务</h4>{tasks.isPending && <p>正在读取任务…</p>}{taskRows.filter((_, index) => ['OPEN', 'ASSIGNED'].includes(tasks.data![index].status))}{tasks.isSuccess && !tasks.data.some(task => ['OPEN', 'ASSIGNED'].includes(task.status)) && <p>暂无待接管或处理中的任务。</p>}{tasks.isError && <p className="form-error">{readableError(tasks.error)}</p>}<h4>待审回复与建议</h4><p className="form-hint">请核对草稿后审批，批准可能按当前策略向客户发布回复。</p>{proposalRows.filter((_, index) => proposals.data![index].status === 'DRAFT')}{proposals.isPending && <p>正在读取草稿…</p>}{proposals.isSuccess && !proposals.data.some(proposal => proposal.status === 'DRAFT') && <p>暂无待审草稿。</p>}{proposals.isError && <p className="form-error">{readableError(proposals.error)}</p>}</>}
      <details className="collaboration-settings" open={compact ? undefined : true}><summary>协作策略与历史记录</summary><p className="policy-summary">当前：{statusLabel(conversation.collaboration_mode)} · 发言策略：{statusLabel(conversation.reply_policy)} · 版本 {conversation.version}</p>
      <div className="collaboration-controls">
        <label>协作模式 <select value={mode} disabled={busy || !active} onChange={(event) => setMode(event.target.value as typeof mode)}>
          <option value="AI_LEAD">AI 主导</option><option value="CO_SERVICE">共同服务</option><option value="HUMAN_LEAD">真人主导</option>
        </select></label>
        <button type="button" disabled={busy || !active || reason.trim().length < 3} onClick={() => void run(() => transitionMode(conversation.id, {
          target_mode: mode, reply_policy: mode === 'AI_LEAD' ? 'AI_AUTO' : mode === 'CO_SERVICE' ? 'AI_REVIEW_REQUIRED' : 'HUMAN_ONLY',
          expected_version: conversation.version, reason: reason.trim(),
        }))}>{busy ? '正在处理…' : '切换策略'}</button>
      </div>
      <h4>{compact ? '其他人工任务' : '人工任务'}</h4>
      {tasks.isError && <p className="form-error">{readableError(tasks.error)}</p>}
      {taskRows.filter((_, index) => !compact || !['OPEN', 'ASSIGNED'].includes(tasks.data![index].status))}
      <h4>{compact ? '已审阅记录' : '助手内部草稿'}</h4>
      {proposals.isError && <p className="form-error">{readableError(proposals.error)}</p>}
      {proposalRows.filter((_, index) => !compact || proposals.data![index].status !== 'DRAFT')}
      </details>
    </>}
    {desk && reason.trim().length < 3 && <p className="form-hint">切换或审阅前，请填写至少 3 个字的原因。</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}
