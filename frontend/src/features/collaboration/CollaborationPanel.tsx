import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { type Actor, type Conversation, claimTask, decideProposal, listProposals, listTasks, requestAssistance, transitionMode } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'

export function CollaborationPanel({ conversation, actor, desk }: { conversation: Conversation, actor: Actor, desk: boolean }) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('需要人工协助处理当前问题')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'AI_LEAD' | 'CO_SERVICE' | 'HUMAN_LEAD'>(conversation.collaboration_mode as 'AI_LEAD' | 'CO_SERVICE' | 'HUMAN_LEAD')
  useEffect(() => setMode(conversation.collaboration_mode as typeof mode), [conversation.collaboration_mode])
  const tasks = useQuery({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id), queryFn: () => listTasks(conversation.id), enabled: desk })
  const proposals = useQuery({ queryKey: queryKeys.proposals(actor.tenant_id, conversation.id), queryFn: () => listProposals(conversation.id), enabled: desk })

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.proposals(actor.tenant_id, conversation.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, conversation.id) }),
      ])
    } catch (failure) {
      setError(readableError(failure))
    } finally {
      setBusy(false)
    }
  }

  return <section className="collaboration-panel" aria-label="人机协作">
    <h3>人机协作</h3>
    <p>当前：{conversation.collaboration_mode} · 发言策略：{conversation.reply_policy} · 版本 {conversation.version}</p>
    {!desk && <button type="button" disabled={busy} onClick={() => void run(() => requestAssistance(conversation.id, reason))}>请求人工协助</button>}
    {desk && <>
      <div className="collaboration-controls">
        <label>协作模式 <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
          <option value="AI_LEAD">AI 主导</option><option value="CO_SERVICE">共同服务</option><option value="HUMAN_LEAD">真人主导</option>
        </select></label>
        <label>原因 <input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} maxLength={1000} /></label>
        <button type="button" disabled={busy || reason.trim().length < 3} onClick={() => void run(() => transitionMode(conversation.id, {
          target_mode: mode, reply_policy: mode === 'AI_LEAD' ? 'AI_AUTO' : mode === 'CO_SERVICE' ? 'AI_REVIEW_REQUIRED' : 'HUMAN_ONLY',
          expected_version: conversation.version, reason: reason.trim(),
        }))}>切换策略</button>
      </div>
      <h4>人工任务</h4>
      {tasks.isError && <p className="form-error">{readableError(tasks.error)}</p>}
      {tasks.data?.length === 0 && <p>暂无人工任务。</p>}
      {tasks.data?.map((task) => <div className="collaboration-item" key={task.id}>
        <span>{task.reason} · {task.status} · 版本 {task.version}</span>
        {task.status === 'OPEN' && <button type="button" disabled={busy} onClick={() => void run(() => claimTask(task.id, task.version))}>接管</button>}
      </div>)}
      <h4>Agent 内部草稿</h4>
      {proposals.isError && <p className="form-error">{readableError(proposals.error)}</p>}
      {proposals.data?.length === 0 && <p>暂无待审草稿。</p>}
      {proposals.data?.map((proposal) => <div className="collaboration-item" key={proposal.id}>
        <span>{proposal.proposal_type} · {String(proposal.payload.summary ?? '')} · {proposal.status}</span>
        {proposal.status === 'DRAFT' && <span>
          <button type="button" disabled={busy} onClick={() => void run(() => decideProposal(proposal.id, 'APPROVED', reason, crypto.randomUUID()))}>批准</button>{' '}
          <button type="button" disabled={busy} onClick={() => void run(() => decideProposal(proposal.id, 'REJECTED', reason, crypto.randomUUID()))}>拒绝</button>
        </span>}
      </div>)}
    </>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section>
}
