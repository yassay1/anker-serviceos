import { type Conversation } from '../../api/client'

export function ConversationSidebar({ desk, items, selectedId, loading, error, creating, createError, onCreate, onSelect }: {
  desk: boolean
  items: Conversation[] | undefined
  selectedId: string | undefined
  loading: boolean
  error?: string
  creating: boolean
  createError: string
  onCreate: () => void
  onSelect: (id: string) => void
}) {
  return <aside className="conversation-list" aria-label="会话列表">
    <div className="section-heading">
      <div><span className="section-kicker">{desk ? '客服收件箱' : '我的服务'}</span><h2>{desk ? '服务会话' : '最近会话'}</h2></div>
      {!desk && <button type="button" onClick={onCreate} disabled={creating}>{creating ? '建立中…' : '新建会话'}</button>}
    </div>
    {createError && <p className="form-error" role="alert">{createError}</p>}
    {loading && <p className="sidebar-hint">正在加载会话…</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {items?.length === 0 && <p className="sidebar-hint">{desk ? '当前暂无可处理的会话。' : '还没有会话。建立会话后即可描述问题。'}</p>}
    <ul>{items?.map((item) => <li key={item.id}>
      <button type="button" className={selectedId === item.id ? 'selected' : ''}
        aria-current={selectedId === item.id ? 'page' : undefined} onClick={() => onSelect(item.id)}>
        <span className="conversation-item-top"><strong>{desk ? `客户 ${item.customer_id.slice(0, 8)}` : '服务会话'}</strong>
          <span className={`conversation-status ${item.status === 'ACTIVE' ? 'active' : ''}`}>{item.status === 'ACTIVE' ? '进行中' : '已归档'}</span></span>
        <span>{new Date(item.created_at).toLocaleDateString('zh-CN')} · 编号 {item.id.slice(0, 8)}</span>
      </button>
    </li>)}</ul>
  </aside>
}
