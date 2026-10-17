import { useQuery } from '@tanstack/react-query'
import { listCustomerAssistance, type Actor } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'

const labels = { OPEN: '已提交，等待客服接手', ASSIGNED: '客服已接手', CLOSED: '任务已关闭' } as const

export function CustomerAssistanceStatus({ actor, conversationId }: { actor: Actor, conversationId: string }) {
  const assistance = useQuery({
    queryKey: queryKeys.customerAssistance(actor.tenant_id, actor.actor_id, conversationId),
    queryFn: () => listCustomerAssistance(conversationId),
    refetchInterval: 10_000,
  })
  return <section className="customer-assistance-status" aria-label="人工协助状态">
    <h4>人工协助状态</h4>
    {assistance.isPending && <p>正在读取服务端状态…</p>}
    {assistance.isSuccess && <button type="button" disabled={assistance.isFetching} onClick={() => void assistance.refetch()}>
      {assistance.isFetching ? '正在刷新…' : '刷新协助状态'}
    </button>}
    {assistance.isError && <div role="alert"><p className="form-error">{readableError(assistance.error)}</p>
      <button type="button" onClick={() => void assistance.refetch()}>重试查询</button></div>}
    {assistance.isSuccess && assistance.data.length === 0 && <p>当前没有人工协助任务。</p>}
    {assistance.data?.map(task => <p key={task.id} data-status={task.status}>{labels[task.status]}</p>)}
  </section>
}
