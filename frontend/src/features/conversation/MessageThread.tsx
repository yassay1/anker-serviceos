import { type Actor, type Message, type SendBody } from '../../api/client'
import { MessageSquareText } from 'lucide-react'

type PendingMessage = {
  conversationId: string
  body: SendBody
  status: 'sending' | 'uncertain' | 'saved'
  error?: string
}

const clock = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' })

function MessageItem({ message, actor }: { message: Message, actor: Actor }) {
  const mine = message.author_kind === actor.kind
  return <li className={`message ${mine ? 'own-message' : ''} ${message.visibility === 'INTERNAL' ? 'internal-message' : ''}`}>
    <div className="message-meta">
      <strong>{message.author_kind === 'CUSTOMER' ? '客户' : message.author_kind === 'STAFF' ? '客服' : '服务助手'}</strong>
      {message.visibility === 'INTERNAL' && <span className="private-tag">内部备注</span>}
      <time dateTime={message.created_at}>{clock.format(new Date(message.created_at))}</time>
    </div>
    {message.content.map((part, index) => <p key={index}>{part.text}</p>)}
  </li>
}

export function MessageThread({ actor, desk, messages, pending, loading, error, hasMore, loadingMore, onMore, onRetry }: {
  actor: Actor
  desk: boolean
  messages: Message[]
  pending: PendingMessage[]
  loading: boolean
  error?: string
  hasMore: boolean
  loadingMore: boolean
  onMore: () => void
  onRetry: (item: PendingMessage) => void
}) {
  return <div className="message-list-wrap">
    {hasMore && <button type="button" className="load-more" disabled={loadingMore} onClick={onMore}>{loadingMore ? '加载中…' : '加载更早消息'}</button>}
    {loading && <p className="message-empty">正在加载消息…</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {!loading && messages.length === 0 && pending.length === 0 && <div className="message-empty"><span className="empty-symbol"><MessageSquareText size={28} aria-hidden="true" /></span><h3>{desk ? '等待这段对话开始' : '你的服务，从这里开始'}</h3>
      <p>{desk ? '客户发送的消息会显示在这里。' : '描述遇到的问题；客服可以在同一会话继续处理。'}</p></div>}
    <ol className="message-list" aria-live="polite">
      {messages.map((message) => <MessageItem key={message.id} message={message} actor={actor} />)}
      {pending.map((item) => <li className={`message own-message pending-message ${item.body.visibility === 'INTERNAL' ? 'internal-message' : ''}`}
        key={item.body.client_message_id}>
        <div className="message-meta"><strong>{desk ? '客服' : '客户'}</strong>
          {item.body.visibility === 'INTERNAL' && <span className="private-tag">内部备注</span>}
          <span>{item.status === 'sending' ? '正在保存…' : item.status === 'saved' ? '已保存，正在同步' : '保存结果未确认'}</span></div>
        <p>{item.body.content.map((part) => part.text).join('\n')}</p>
        {item.status === 'uncertain' && <div className="retry-row"><span role="alert">{item.error}</span>
          <button type="button" onClick={() => onRetry(item)}>用原消息重试</button></div>}
      </li>)}
    </ol>
  </div>
}
