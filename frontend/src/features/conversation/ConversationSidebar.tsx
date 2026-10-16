import { useState } from 'react'
import { MessageSquare, Plus, Search } from 'lucide-react'
import { type Conversation } from '../../api/client'
import { StatusBadge, statusLabel } from '../../shared/StatusBadge'

export function ConversationSidebar({ desk, items, selectedId, loading, error, creating, createError, onCreate, onSelect }: {
  desk: boolean, items: Conversation[] | undefined, selectedId: string | undefined,
  loading: boolean, error?: string, creating: boolean, createError: string,
  onCreate: () => void, onSelect: (id: string) => void,
}) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('ALL')
  const visible = items?.filter(item => (filter === 'ALL' || item.status === filter) &&
    `${item.title} ${item.id} ${item.customer_id}`.toLowerCase().includes(search.trim().toLowerCase()))
  return <aside className="conversation-list" aria-label="会话列表">
    <div className="section-heading"><h2>{desk ? '服务会话' : '我的服务'}</h2>
      {!desk && <button type="button" className="icon-button" aria-label={creating ? '建立中…' : '新建会话'} onClick={onCreate} disabled={creating}><Plus size={18} aria-hidden="true" /></button>}
    </div>
    <div className="sidebar-search"><Search size={16} aria-hidden="true" /><input aria-label="搜索已加载的会话" placeholder="搜索问题、会话或客户编号" value={search} onChange={e => setSearch(e.target.value)} /></div>
    <div className="list-filters" aria-label="会话状态筛选">{[['ALL', '全部'], ['ACTIVE', '进行中'], ['ARCHIVED', '已归档']].map(([value, label]) =>
      <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
    <p className="list-count">{loading ? '正在读取记录' : `已加载 ${items?.length ?? 0} 条会话`}</p>
    {createError && <p className="form-error" role="alert">{createError}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {loading && <div className="skeleton-list" aria-label="正在加载会话"><span /><span /><span /></div>}
    {!loading && visible?.length === 0 && <div className="sidebar-empty"><MessageSquare aria-hidden="true" /><p>{search || filter !== 'ALL' ? '没有匹配的会话' : desk ? '当前暂无可处理的会话' : '还没有服务记录'}</p><small>{search || filter !== 'ALL' ? '试试其他编号或查看全部会话。' : desk ? '客户的会话会在这里出现。' : '新建会话，告诉我们遇到的问题。'}</small></div>}
    <ul>{visible?.map(item => <li key={item.id}>
      <button type="button" className={selectedId === item.id ? 'selected' : ''} aria-current={selectedId === item.id ? 'page' : undefined} onClick={() => onSelect(item.id)}>
        <span className="conversation-item-top"><strong title={item.title}>{item.title || '新会话'}</strong><StatusBadge value={item.status} /></span>
        <span className="conversation-mode">{desk ? `客户 ${item.customer_id.slice(0, 8)} · ` : ''}{statusLabel(item.collaboration_mode)}</span>
        <span className="conversation-item-bottom"><span>#{item.id.slice(0, 8)}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}</time></span>
      </button>
    </li>)}</ul>
  </aside>
}
