import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import {
  type Actor, type Message, type SendBody,
  createConversation, listConversations, listMessages, loginLocal, logout,
  readActor, readHealth, sendMessage,
} from './api/client'

type Pending = {
  conversationId: string
  body: SendBody
  status: 'sending' | 'uncertain' | 'saved'
  error?: string
}

const clock = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' })

function readableError(error: unknown) {
  return error instanceof Error ? error.message : '服务暂时不可用，请稍后重试。'
}

function ConnectionStatus() {
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => readHealth(signal) })
  return (
    <div className="connection" aria-label="本地服务连接状态">
      <span role="status" aria-live="polite">
        <span className={`status-dot ${health.isError ? 'offline' : ''}`} aria-hidden="true" />
        {health.isFetching ? '正在检查服务' : health.isError ? '本地服务未连接' : '本地服务已连接'}
      </span>
      <button type="button" disabled={health.isFetching} onClick={() => void health.refetch()}>重新检查</button>
    </div>
  )
}

function LoginPanel() {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('customer-a')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const actor = await loginLocal(username, password)
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'actor' })
      queryClient.setQueryData(['actor'], actor)
      setPassword('')
    } catch (failure) {
      setError(readableError(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="login-card" aria-labelledby="login-title">
      <p className="eyebrow">本地开发体验</p>
      <h1 id="login-title">进入售后通</h1>
      <p>使用本地测试身份查看真实保存的会话。此登录入口仅在开发环境启用。</p>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="account">体验身份</label>
        <select id="account" value={username} onChange={(event) => setUsername(event.target.value)}>
          <option value="customer-a">客户 A</option>
          <option value="customer-b">客户 B</option>
          <option value="staff">客服</option>
          <option value="other-tenant">另一租户客户</option>
        </select>
        <label htmlFor="password">本地体验密码</label>
        <input id="password" type="password" autoComplete="current-password" value={password}
          onChange={(event) => setPassword(event.target.value)} required />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" className="primary-button" disabled={busy}>{busy ? '正在进入…' : '进入工作区'}</button>
      </form>
      <p className="form-hint">体验密码见本项目本地配置说明。请勿输入真实客户或设备资料。</p>
      <ConnectionStatus />
    </section>
  )
}

function AccountHeader({ actor }: { actor: Actor }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState('')

  async function signOut() {
    try {
      await logout()
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'actor' })
      queryClient.setQueryData(['actor'], null)
    } catch (failure) {
      setError(readableError(failure))
    }
  }

  return (
    <div className="account-strip">
      <span>{actor.display_name} · {actor.kind === 'STAFF' ? '客服' : '客户'}</span>
      <button type="button" onClick={() => void signOut()}>退出登录</button>
      {error && <span className="form-error" role="alert">{error}</span>}
    </div>
  )
}

function MessageItem({ message, actor }: { message: Message, actor: Actor }) {
  const mine = message.author_kind === actor.kind
  return (
    <li className={`message ${mine ? 'own-message' : ''} ${message.visibility === 'INTERNAL' ? 'internal-message' : ''}`}>
      <div className="message-meta">
        <strong>{message.author_kind === 'CUSTOMER' ? '客户' : message.author_kind === 'STAFF' ? '客服' : '系统'}</strong>
        {message.visibility === 'INTERNAL' && <span className="private-tag">内部备注</span>}
        <time dateTime={message.created_at}>{clock.format(new Date(message.created_at))}</time>
      </div>
      {message.content.map((part, index) => <p key={index}>{part.text}</p>)}
    </li>
  )
}

function ConversationWorkspace({ actor, desk }: { actor: Actor, desk: boolean }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState('')
  const [internal, setInternal] = useState(false)
  const [pending, setPending] = useState<Pending[]>([])

  const conversations = useQuery({
    queryKey: ['conversations', actor.tenant_id, actor.actor_id], queryFn: listConversations,
    refetchInterval: 10_000,
  })
  const selectedId = searchParams.get('conversation')
  const selected = conversations.data?.find((item) => item.id === selectedId) ?? (
    selectedId ? undefined : conversations.data?.[0]
  )
  const messageQueryKey = ['messages', actor.tenant_id, actor.actor_id, selected?.id]
  const messages = useInfiniteQuery({
    queryKey: messageQueryKey,
    queryFn: ({ pageParam }) => listMessages(selected!.id, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(selected),
    refetchInterval: 4_000,
  })
  const recorded = messages.data?.pages.flatMap((page) => page.items) ?? []
  const recordedKeys = new Set(recorded.map((message) => message.client_message_id))
  const visiblePending = pending.filter((item) => item.conversationId === selected?.id && !recordedKeys.has(item.body.client_message_id))

  async function startConversation() {
    setCreating(true)
    setCreateError('')
    try {
      const created = await createConversation()
      await queryClient.invalidateQueries({ queryKey: ['conversations', actor.tenant_id, actor.actor_id] })
      setSearchParams({ conversation: created.id })
    } catch (failure) {
      setCreateError(readableError(failure))
    } finally {
      setCreating(false)
    }
  }

  async function deliver(item: Pending) {
    setPending((current) => current.map((part) => part.body.client_message_id === item.body.client_message_id
      ? { ...part, status: 'sending', error: undefined } : part))
    try {
      await sendMessage(item.conversationId, item.body)
      setPending((current) => current.map((part) => part.body.client_message_id === item.body.client_message_id
        ? { ...part, status: 'saved', error: undefined } : part))
      await queryClient.invalidateQueries({ queryKey: messageQueryKey })
    } catch (failure) {
      setPending((current) => current.map((part) => part.body.client_message_id === item.body.client_message_id
        ? { ...part, status: 'uncertain', error: readableError(failure) } : part))
    }
  }

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || !draft.trim() || draft.length > 8000) return
    const item: Pending = {
      conversationId: selected.id,
      body: {
        client_message_id: crypto.randomUUID(),
        content: [{ type: 'text', text: draft.trim() }],
        visibility: desk && internal ? 'INTERNAL' : 'PUBLIC',
      },
      status: 'sending',
    }
    setPending((current) => [...current, item])
    setDraft('')
    void deliver(item)
  }

  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">{desk ? '客服工作区' : '用户服务'}</p>
        <h1>{desk ? '服务会话' : '你的服务会话'}</h1>
        <p>{desk ? '查看同租户会话并回复；内部备注只对客服可见。' : '发送问题后可刷新页面，已保存的消息会重新出现。'}</p>
      </div>
      <div className="chat-layout">
        <aside className="conversation-list" aria-label="会话列表">
          <div className="section-heading">
            <h2>会话</h2>
            {!desk && <button type="button" onClick={() => void startConversation()} disabled={creating}>
              {creating ? '建立中…' : '新建会话'}
            </button>}
          </div>
          {createError && <p className="form-error" role="alert">{createError}</p>}
          {conversations.isPending && <p className="sidebar-hint">正在加载会话…</p>}
          {conversations.isError && <p className="form-error" role="alert">{readableError(conversations.error)}</p>}
          {conversations.data?.length === 0 && <p className="sidebar-hint">{desk ? '当前暂无会话。' : '还没有会话，开始一个新会话吧。'}</p>}
          <ul>
            {conversations.data?.map((item) => <li key={item.id}>
              <button type="button" className={selected?.id === item.id ? 'selected' : ''}
                aria-current={selected?.id === item.id ? 'page' : undefined}
                onClick={() => setSearchParams({ conversation: item.id })}>
                <strong>{desk ? `客户 ${item.customer_id.slice(0, 8)}` : '服务会话'}</strong>
                <span>{new Date(item.created_at).toLocaleDateString('zh-CN')} · {item.status === 'ACTIVE' ? '进行中' : '已归档'}</span>
              </button>
            </li>)}
          </ul>
        </aside>
        <section className="chat-panel" aria-label="当前会话">
          {selected ? <>
            <div className="chat-heading">
              <div><h2>{desk ? '与客户沟通' : '当前服务会话'}</h2><p>会话编号 {selected.id.slice(0, 8)}</p></div>
              <span className="state-pill">{selected.status === 'ACTIVE' ? '进行中' : '已归档'}</span>
            </div>
            <div className="message-list-wrap">
              {messages.hasNextPage && <button type="button" className="load-more" disabled={messages.isFetchingNextPage}
                onClick={() => void messages.fetchNextPage()}>{messages.isFetchingNextPage ? '加载中…' : '加载更多消息'}</button>}
              {messages.isPending && <p className="message-empty">正在加载消息…</p>}
              {messages.isError && <p className="form-error" role="alert">{readableError(messages.error)}</p>}
              {!messages.isPending && recorded.length === 0 && visiblePending.length === 0 &&
                <div className="message-empty"><h3>从这里开始</h3><p>描述遇到的问题；客服可以在同一会话继续处理。</p></div>}
              <ol className="message-list" aria-live="polite">
                {recorded.map((message) => <MessageItem key={message.id} message={message} actor={actor} />)}
                {visiblePending.map((item) => <li className={`message own-message pending-message ${item.body.visibility === 'INTERNAL' ? 'internal-message' : ''}`}
                  key={item.body.client_message_id}>
                  <div className="message-meta"><strong>{desk ? '客服' : '客户'}</strong>
                    {item.body.visibility === 'INTERNAL' && <span className="private-tag">内部备注</span>}
                    <span>{item.status === 'sending' ? '正在保存…' : item.status === 'saved' ? '已保存，正在同步' : '保存结果未确认'}</span></div>
                  <p>{item.body.content.map((part) => part.text).join('\n')}</p>
                  {item.status === 'uncertain' && <div className="retry-row">
                    <span role="alert">{item.error}</span>
                    <button type="button" onClick={() => void deliver(item)}>用原消息重试</button>
                  </div>}
                </li>)}
              </ol>
            </div>
            <form className="composer" onSubmit={submitMessage}>
              <label htmlFor="message-draft">{desk ? '回复客户' : '描述你的问题'}</label>
              <textarea id="message-draft" value={draft} maxLength={8000} rows={3}
                onChange={(event) => setDraft(event.target.value)} disabled={selected.status !== 'ACTIVE'}
                placeholder={desk ? '输入回复；可勾选为内部备注' : '例如：充电器连接后指示灯没有亮…'} />
              {desk && <label className="checkbox-label"><input type="checkbox" checked={internal}
                onChange={(event) => setInternal(event.target.checked)} /> 仅客服可见的内部备注</label>}
              <div className="composer-foot">
                <p>{desk ? '公开回复会显示给客户。' : '消息会保存；自动回复尚未接入。'}</p>
                <button type="submit" className="primary-button" disabled={!draft.trim() || selected.status !== 'ACTIVE'}>发送消息</button>
              </div>
            </form>
          </> : <div className="message-empty"><h2>{selectedId ? '会话不可访问' : '选择一个会话'}</h2>
            <p>{selectedId ? '请从左侧选择有权限查看的会话。' : desk ? '从左侧打开客户会话。' : '新建会话后即可发送消息。'}</p></div>}
        </section>
      </div>
      <p className="phase-note">当前阶段：消息、案例与设备资料已持久化；Agent 处理、实时推送和协作模式切换将在后续阶段接入。</p>
      <ConnectionStatus />
    </>
  )
}

function ServicePage({ desk = false }: { desk?: boolean }) {
  const actor = useQuery({ queryKey: ['actor'], queryFn: readActor, retry: false, staleTime: 0 })
  if (actor.isPending) return <p className="loading-state">正在确认登录状态…</p>
  if (actor.isError || !actor.data) return <LoginPanel />
  if (desk && actor.data.kind !== 'STAFF') return <section className="access-note">
    <h1>此页面仅供客服使用</h1><p>当前身份是客户，请使用用户服务入口。</p><NavLink to="/support">返回用户服务</NavLink>
  </section>
  if (!desk && actor.data.kind === 'STAFF') return <section className="access-note">
    <h1>已以客服身份登录</h1><p>请到客服工作区查看会话。</p><NavLink to="/desk">前往客服工作区</NavLink>
  </section>
  return <><AccountHeader actor={actor.data} /><ConversationWorkspace actor={actor.data} desk={desk} /></>
}

export function App() {
  return <>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="site-header"><div className="header-inner">
      <NavLink className="brand" to="/support"><span>售后通</span><small>Anker ServiceOS</small></NavLink>
      <nav aria-label="主要导航"><NavLink to="/support">用户服务</NavLink><NavLink to="/desk">客服工作区</NavLink></nav>
    </div></header>
    <main id="main-content" tabIndex={-1}>
      <Routes>
        <Route path="/" element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<ServicePage />} />
        <Route path="/desk" element={<ServicePage desk />} />
        <Route path="*" element={<section><h1>未找到这个页面</h1><NavLink to="/support">返回用户服务</NavLink></section>} />
      </Routes>
    </main>
    <footer>售后通 · 本地开发体验</footer>
  </>
}
