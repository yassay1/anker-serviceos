import { useEffect, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { MessagesSquare, X } from 'lucide-react'
import { type Actor, type ServiceCase, listConversations, listDeskCaseSummaries } from '../api/client'
import { queryKeys } from '../app/queryKeys'
import { readableError } from './errors'
import { StatusBadge } from './StatusBadge'

/** Resolve actual case links, never assume that the customer's first conversation is the case. */
export function CaseConversationPicker({ actor, serviceCase, label = '进入服务会话', className = 'primary-button' }: {
  actor: Actor, serviceCase: ServiceCase, label?: string, className?: string,
}) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations, enabled: open })
  const candidates = conversations.data?.filter(item => item.customer_id === serviceCase.customer_id) ?? []
  const summaries = useQueries({ queries: open ? candidates.map(item => ({
    queryKey: queryKeys.summaries(actor.tenant_id, item.id), queryFn: () => listDeskCaseSummaries(item.id), staleTime: 0,
  })) : [] })
  const waiting = conversations.isPending || conversations.isFetching || summaries.some(item => item.isPending || item.isFetching)
  const failure = conversations.error ?? summaries.find(item => item.isError)?.error
  const matches = candidates.filter((_, index) => summaries[index]?.data?.some(item => item.case.id === serviceCase.id))
  useEffect(() => {
    if (open && !waiting && !failure && matches.length === 1) {
      setOpen(false)
      navigate(`/desk?conversation=${matches[0].id}`)
    }
  }, [open, waiting, failure, matches.map(item => item.id).join(','), navigate])

  return <div className="case-conversation-picker">
    <button type="button" className={className} onClick={() => setOpen(value => !value)} aria-expanded={open}><MessagesSquare size={17} />{label}</button>
    {open && <section className="case-conversation-options" aria-label="选择关联服务会话"><header><strong>关联服务会话</strong><button type="button" className="icon-button" aria-label="关闭会话选择" onClick={() => setOpen(false)}><X size={16} /></button></header>
      {waiting && <p role="status">正在核对案例与会话的关联…</p>}
      {failure && <div role="alert"><p>{readableError(failure)}</p><button type="button" onClick={() => { void conversations.refetch(); summaries.forEach(item => void item.refetch()) }}>重新查询</button></div>}
      {!waiting && matches.length > 0 && <><p>选择要继续处理的会话：</p>{matches.map(item => <Link key={item.id} to={`/desk?conversation=${item.id}`}><span>{item.title || '服务会话'}</span><StatusBadge value={item.status} /><small>建于 {new Date(item.created_at).toLocaleString('zh-CN')}</small></Link>)}</>}
      {!waiting && !failure && matches.length === 0 && <p>当前已加载的会话中没有此案例的关联记录。可在服务会话中核对或建立关联。</p>}
    </section>}
  </div>
}
