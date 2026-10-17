import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiFailure, type Actor, type Conversation, approveReplyDraft, claimTask, createReplyDraft, decideProposal,
  listProposals, listReplyDrafts, listTasks, listTaskQueue, sendReplyDraft, transitionMode, updateReplyDraft } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { UsersRound } from 'lucide-react'
import { statusLabel } from '../../shared/StatusBadge'

export function CollaborationPanel({ conversation, actor, desk, compact = false }: { conversation: Conversation, actor: Actor, desk: boolean, compact?: boolean }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [reason, setReason] = useState('需要人工协助处理当前问题')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const active = conversation.status === 'ACTIVE'
  const [mode, setMode] = useState<'AI_LEAD' | 'CO_SERVICE' | 'HUMAN_LEAD'>(conversation.collaboration_mode as 'AI_LEAD' | 'CO_SERVICE' | 'HUMAN_LEAD')
  const [queue, setQueue] = useState<'OPEN' | 'MINE'>('OPEN')
  const [queueCursor, setQueueCursor] = useState<string | undefined>()
  const [replyEdits, setReplyEdits] = useState<Record<string, string>>({})
  useEffect(() => setMode(conversation.collaboration_mode as typeof mode), [conversation.collaboration_mode, conversation.version])
  const tasks = useQuery({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id), queryFn: () => listTasks(conversation.id), enabled: desk, refetchInterval: 10_000 })
  const proposals = useQuery({ queryKey: queryKeys.proposals(actor.tenant_id, conversation.id), queryFn: () => listProposals(conversation.id), enabled: desk, refetchInterval: 10_000 })
  const replyDrafts = useQuery({ queryKey: queryKeys.replyDrafts(actor.tenant_id, conversation.id), queryFn: () => listReplyDrafts(conversation.id), enabled: desk, refetchInterval: 10_000 })
  const queuePage = useQuery({ queryKey: [...queryKeys.taskQueue(actor.tenant_id, actor.actor_id, queue), queueCursor],
    queryFn: () => listTaskQueue(queue, queueCursor), enabled: desk && compact,
    refetchInterval: query => query.state.status === 'error' ? false : 10_000 })

  async function refreshState() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, conversation.id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.proposals(actor.tenant_id, conversation.id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.replyDrafts(actor.tenant_id, conversation.id) }),
      queryClient.invalidateQueries({ queryKey: ['task-queue', actor.tenant_id, actor.actor_id] }),
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
  const proposalRows = (proposals.data ?? []).filter(proposal => proposal.status === 'DRAFT').map(proposal => <div className="collaboration-item" key={proposal.id}>
    <span>{proposal.proposal_type === 'REPLY' ? '未发布 AI 回复建议' : proposal.proposal_type} · {String(proposal.payload.summary ?? '')}</span>
    {proposal.proposal_type === 'REPLY' && <button type="button" disabled={busy || !active} onClick={() => void run(async () => {
      await createReplyDraft(proposal.id, crypto.randomUUID())
      await queryClient.invalidateQueries({ queryKey: queryKeys.replyDrafts(actor.tenant_id, conversation.id) })
    })}>放入回复框</button>}
    <button type="button" disabled={busy || !active} onClick={() => void run(() => decideProposal(proposal.id, 'REJECTED', '客服忽略此建议', crypto.randomUUID()))}>忽略建议</button>
  </div>)
  const draftRows = (replyDrafts.data ?? []).map(draft => {
    const text = replyEdits[draft.id] ?? draft.content
    const dirty = text !== draft.content
    const token = (key: string) => {
      const storageKey = `serviceos:${key}:${draft.id}`
      let value = sessionStorage.getItem(storageKey)
      if (!value) { value = crypto.randomUUID(); sessionStorage.setItem(storageKey, value) }
      return { storageKey, value }
    }
    return <div className="collaboration-item reply-draft-editor" key={draft.id}>
      <label>客服回复草稿 · {statusLabel(draft.status)} · 版本 {draft.version}
        <textarea value={text} disabled={draft.status === 'SENT' || draft.status === 'APPROVED'} maxLength={8000}
          onChange={event => setReplyEdits(current => ({ ...current, [draft.id]: event.target.value }))} />
      </label>
      {dirty && <button type="button" disabled={busy || !text.trim()} onClick={() => void run(async () => {
        const saved = await updateReplyDraft(draft.id, draft.version, text)
        setReplyEdits(current => ({ ...current, [draft.id]: saved.content }))
        await queryClient.invalidateQueries({ queryKey: queryKeys.replyDrafts(actor.tenant_id, conversation.id) })
      })}>保存编辑</button>}
      {['IN_COMPOSER', 'EDITED'].includes(draft.status) && <button type="button" disabled={busy || dirty || !active} onClick={() => void run(async () => {
        const key = token('reply-draft-approval')
        await approveReplyDraft(draft.id, key.value, draft.version)
        sessionStorage.removeItem(key.storageKey)
        await queryClient.invalidateQueries({ queryKey: queryKeys.replyDrafts(actor.tenant_id, conversation.id) })
      })}>单独审批</button>}
      {draft.status === 'APPROVED' && <button type="button" disabled={busy || !active} onClick={() => void run(async () => {
        const key = token('reply-draft-send')
        await sendReplyDraft(draft.id, key.value, draft.version)
        sessionStorage.removeItem(key.storageKey)
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: queryKeys.replyDrafts(actor.tenant_id, conversation.id) }),
          queryClient.invalidateQueries({ queryKey: queryKeys.messages(actor.tenant_id, actor.actor_id, conversation.id) }),
        ])
      })}>发送公开回复</button>}
    </div>
  })
  return <section className="collaboration-panel" aria-label="人机协作">
    <h3><UsersRound size={18} aria-hidden="true" />{desk ? compact ? '待接管与回复审批' : '人机协作' : '需要真人一起处理？'}</h3>
    {!compact && <p className="policy-summary">当前：{statusLabel(conversation.collaboration_mode)} · 发言策略：{statusLabel(conversation.reply_policy)} · 版本 {conversation.version}</p>}
    {!active && <p className="form-hint">此会话已归档，协作操作已停止。</p>}
    {!desk && <p>已有会话会继续保留。请在下方服务交互卡提交人工协助请求；卡片暂不可用时，可在文字消息中说明需求。</p>}
    {desk && <>
      <label className="collaboration-reason">原因 <input value={reason} disabled={busy || !active} onChange={(event) => setReason(event.target.value)} minLength={3} maxLength={1000} /></label>
      {compact && <><h4>任务收件箱</h4><div className="collaboration-controls" role="group" aria-label="任务队列">
        <button type="button" aria-pressed={queue === 'OPEN'} onClick={() => { setQueue('OPEN'); setQueueCursor(undefined) }}>待接任务</button>
        <button type="button" aria-pressed={queue === 'MINE'} onClick={() => { setQueue('MINE'); setQueueCursor(undefined) }}>我已接手</button>
      </div>
      {queuePage.isPending && <p>正在读取任务队列…</p>}
      {queuePage.isError && <div className="form-error" role="alert"><p>{readableError(queuePage.error)}</p><button type="button" onClick={() => void queuePage.refetch()}>重试任务队列</button></div>}
      {queuePage.data?.items?.map(task => <div className="collaboration-item" key={task.id}>
        <span>{task.reason} · {statusLabel(task.status)} · 版本 {task.version}</span>
        <button type="button" onClick={() => navigate(`/desk?conversation=${task.conversation_id}`)}>打开会话</button>
        {queue === 'OPEN' && task.status === 'OPEN' && <button type="button" disabled={busy} onClick={() => void run(() => claimTask(task.id, task.version))}>接收任务</button>}
      </div>)}
      {queuePage.isSuccess && !queuePage.data?.items?.length && <p>此队列当前没有任务。</p>}
      {queuePage.data?.next_cursor && <button type="button" disabled={queuePage.isFetching} onClick={() => setQueueCursor(queuePage.data!.next_cursor!)}>下一页</button>}
      <h4>当前会话任务</h4>{tasks.isPending && <p>正在读取任务…</p>}{taskRows.filter((_, index) => ['OPEN', 'ASSIGNED'].includes(tasks.data![index].status))}{tasks.isSuccess && !tasks.data.some(task => ['OPEN', 'ASSIGNED'].includes(task.status)) && <p>暂无待接管或处理中的任务。</p>}{tasks.isError && <p className="form-error">{readableError(tasks.error)}</p>}
      <h4>未发布 AI 建议</h4><p className="form-hint">放入回复框、编辑、审批、发送是独立步骤。只有单独发送并收到服务端回执后，客户才会看到公开回复。</p>{proposalRows}{proposals.isPending && <p>正在读取建议…</p>}{proposals.isSuccess && !proposalRows.length && <p>暂无未发布建议。</p>}{proposals.isError && <p className="form-error">{readableError(proposals.error)}</p>}
      <h4>客服回复草稿</h4>{draftRows}{replyDrafts.isPending && <p>正在读取已保存草稿…</p>}{replyDrafts.isSuccess && !draftRows.length && <p>暂无已保存草稿。</p>}{replyDrafts.isError && <p className="form-error">{readableError(replyDrafts.error)}</p>}</>}
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
