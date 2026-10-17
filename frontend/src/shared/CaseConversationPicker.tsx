import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { MessagesSquare, X } from 'lucide-react'
import { type Actor, type ServiceCase, listCaseConversations } from '../api/client'
import { queryKeys } from '../app/queryKeys'
import { readableError } from './errors'
import { StatusBadge } from './StatusBadge'

/** Resolve actual case links, never assume that the customer's first conversation is the case. */
export function CaseConversationPicker({ actor, serviceCase, label = '进入服务会话', className = 'primary-button' }: {
  actor: Actor, serviceCase: ServiceCase, label?: string, className?: string,
}) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const conversations = useQuery({ queryKey: queryKeys.caseConversations(actor.tenant_id, actor.actor_id, serviceCase.id),
    queryFn: () => listCaseConversations(serviceCase.id), enabled: open })
  const matches = conversations.data ?? []
  useEffect(() => {
    if (open && conversations.isSuccess && matches.length === 1) {
      setOpen(false)
      navigate(`${actor.kind === 'STAFF' ? '/desk' : '/support'}?conversation=${matches[0].id}`)
    }
  }, [actor.kind, open, conversations.isSuccess, matches.map(item => item.id).join(','), navigate])
  const waiting = conversations.isPending || conversations.isFetching

  return <div className="case-conversation-picker">
    <button type="button" className={className} onClick={() => setOpen(value => !value)} aria-expanded={open}><MessagesSquare size={17} />{label}</button>
    {open && <section className="case-conversation-options" aria-label="选择关联服务会话"><header><strong>关联服务会话</strong><button type="button" className="icon-button" aria-label="关闭会话选择" onClick={() => setOpen(false)}><X size={16} /></button></header>
      {waiting && <p role="status">正在核对案例与会话的关联…</p>}
      {conversations.isError && <div role="alert"><p>{readableError(conversations.error)}</p><button type="button" onClick={() => void conversations.refetch()}>重新查询</button></div>}
      {!waiting && matches.length > 1 && <><p>此服务记录关联多个会话，请选择要继续处理的对话：</p>{matches.map(item => <Link key={item.id} to={`${actor.kind === 'STAFF' ? '/desk' : '/support'}?conversation=${item.id}`}><span>{item.title || '服务会话'}</span><StatusBadge value={item.status} /><small>建于 {new Date(item.created_at).toLocaleString('zh-CN')}</small></Link>)}</>}
      {!waiting && matches.length === 0 && <><p>此服务记录当前没有关联的服务会话。</p>{actor.kind === 'CUSTOMER' && <Link to="/support">查看历史对话或开始新对话</Link>}</>}
    </section>}
  </div>
}
