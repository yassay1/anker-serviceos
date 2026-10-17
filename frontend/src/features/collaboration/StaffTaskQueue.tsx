import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiFailure, claimTask, listTaskQueue, type Actor } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'

export function StaffTaskQueue({ actor, onOpenConversation }: { actor: Actor, onOpenConversation?: (conversationId: string) => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [queue, setQueue] = useState<'OPEN' | 'MINE'>('OPEN')
  const [cursor, setCursor] = useState<string | undefined>()
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')
  const page = useQuery({
    queryKey: [...queryKeys.taskQueue(actor.tenant_id, actor.actor_id, queue), cursor],
    queryFn: () => listTaskQueue(queue, cursor),
    refetchInterval: query => query.state.status === 'error' ? false : 10_000,
  })

  function openConversation(conversationId: string) {
    onOpenConversation?.(conversationId)
    navigate(`/desk?conversation=${conversationId}`)
  }

  async function claim(taskId: string, version: number, conversationId: string) {
    setBusyId(taskId)
    setActionError('')
    try {
      await claimTask(taskId, version)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['task-queue', actor.tenant_id, actor.actor_id] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, conversationId) }),
      ])
      openConversation(conversationId)
    } catch (failure) {
      setActionError(readableError(failure))
      if (failure instanceof ApiFailure && failure.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ['task-queue', actor.tenant_id, actor.actor_id] })
      }
    } finally {
      setBusyId(null)
    }
  }

  return <section className="staff-task-queue" aria-labelledby="staff-task-queue-title">
    <div className="staff-task-queue-heading"><div><h2 id="staff-task-queue-title">人工任务队列</h2><p>任务与服务案例是独立记录。</p></div>
      <Link to="/cases">查看服务案例</Link></div>
    <div className="staff-task-queue-tabs" role="group" aria-label="人工任务队列范围">
      <button type="button" aria-pressed={queue === 'OPEN'} onClick={() => { setQueue('OPEN'); setCursor(undefined) }}>待接任务</button>
      <button type="button" aria-pressed={queue === 'MINE'} onClick={() => { setQueue('MINE'); setCursor(undefined) }}>我已接手</button>
    </div>
    {page.isPending && <p role="status">正在读取人工任务…</p>}
    {page.isError && <div role="alert" className="form-error"><p>{readableError(page.error)}</p><button type="button" onClick={() => void page.refetch()}>重试</button></div>}
    {actionError && <p role="alert" className="form-error">{actionError}</p>}
    {page.data?.items.map(task => <article className="staff-task-row" key={task.id}>
      <div><strong>{task.reason}</strong><p><StatusBadge value={task.status} /> · {new Date(task.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</p>
        {task.case_id && <small>关联案例 #{task.case_id.slice(0, 8)}</small>}</div>
      <div className="staff-task-actions"><button type="button" onClick={() => openConversation(task.conversation_id)}>打开会话</button>
        {queue === 'OPEN' && task.status === 'OPEN' && <button type="button" disabled={busyId === task.id} onClick={() => void claim(task.id, task.version, task.conversation_id)}>{busyId === task.id ? '正在接手…' : '接手任务'}</button>}</div>
    </article>)}
    {page.isSuccess && !page.data.items.length && <p className="empty-note">此任务队列当前没有记录。</p>}
    {page.data?.next_cursor && <button type="button" disabled={page.isFetching} onClick={() => setCursor(page.data!.next_cursor!)}>下一页</button>}
  </section>
}
