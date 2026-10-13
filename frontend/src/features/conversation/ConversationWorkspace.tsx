import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FileText, Headphones, Inbox, MessageSquare, ShieldCheck } from 'lucide-react'
import {
  type Actor, type SendBody, createConversation, listConversations,
  listDeskCaseSummaries, listMessages, readUIDocument, refreshUIDocument, sendMessage,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { ConnectionStatus } from '../../shared/ConnectionStatus'
import { CollaborationPanel } from '../collaboration/CollaborationPanel'
import { UIDocumentRenderer } from '../ui-document/UIDocumentRenderer'
import { useConversationEvents } from './useConversationEvents'
import { ConversationSidebar } from './ConversationSidebar'
import { MessageThread } from './MessageThread'
import { MessageComposer } from './MessageComposer'
import { StatusBadge } from '../../shared/StatusBadge'

type Pending = {
  conversationId: string
  body: SendBody
  status: 'sending' | 'uncertain' | 'saved'
  error?: string
}

export function ConversationWorkspace({ actor, desk }: { actor: Actor, desk: boolean }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)
  const [drafts, setDrafts] = useState<Record<string, { text: string, internal: boolean }>>({})
  const [mobilePanel, setMobilePanel] = useState<'list' | 'chat' | 'context'>('chat')
  const [pending, setPending] = useState<Pending[]>([])
  const conversations = useQuery({
    queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations,
    refetchInterval: 10_000,
  })
  const selectedId = searchParams.get('conversation')
  const selected = conversations.data?.find((item) => item.id === selectedId) ?? (
    selectedId ? undefined : conversations.data?.[0]
  )
  const draft = selected ? drafts[selected.id]?.text ?? '' : ''
  const internal = selected ? drafts[selected.id]?.internal ?? false : false
  function setDraft(text: string) {
    if (selected) setDrafts(current => ({ ...current, [selected.id]: { text, internal: current[selected.id]?.internal ?? false } }))
  }
  function setInternal(value: boolean) {
    if (selected) setDrafts(current => ({ ...current, [selected.id]: { text: current[selected.id]?.text ?? '', internal: value } }))
  }
  const streamState = useConversationEvents(actor, selected?.id, desk)
  const messageQueryKey = queryKeys.messages(actor.tenant_id, actor.actor_id, selected?.id ?? '')
  const messages = useInfiniteQuery({
    queryKey: messageQueryKey,
    queryFn: ({ pageParam }) => listMessages(selected!.id, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(selected),
    // Transport-open does not prove the independent Outbox dispatcher is running.
    refetchInterval: streamState === 'connected' ? 10_000 : 4_000,
  })
  // The API cursor moves forward from the oldest message, so read to the tail.
  // A failed page pauses automatic fetching and leaves an explicit retry control.
  useEffect(() => {
    if (messages.hasNextPage && !messages.isFetching && !messages.isError) {
      void messages.fetchNextPage()
    }
  }, [messages.hasNextPage, messages.isFetching, messages.isError, messages.fetchNextPage])
  const summaries = useQuery({
    queryKey: queryKeys.summaries(actor.tenant_id, selected?.id ?? ''),
    queryFn: () => listDeskCaseSummaries(selected!.id),
    enabled: desk && Boolean(selected),
    refetchInterval: 10_000,
  })
  const uiDocument = useQuery({
    queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected?.id ?? ''),
    queryFn: () => selected!.status === 'ACTIVE' ? refreshUIDocument(selected!.id) : readUIDocument(selected!.id),
    enabled: Boolean(selected),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: 10_000,
  })
  const recorded = messages.data?.pages.flatMap((page) => page.items) ?? []
  const recordedKeys = new Set(recorded.map((message) => message.client_message_id))
  const visiblePending = pending.filter((item) => item.conversationId === selected?.id && !recordedKeys.has(item.body.client_message_id))

  async function startConversation() {
    setCreating(true)
    setCreateError('')
    try {
      const created = await createConversation()
      await queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      setSearchParams({ conversation: created.id })
      setMobilePanel('chat')
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
      await queryClient.invalidateQueries({ queryKey: queryKeys.messages(actor.tenant_id, actor.actor_id, item.conversationId) })
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

  return <div className={`workspace-page ${desk ? 'desk-view' : 'support-view'} mobile-${mobilePanel}`}>
    <div className="page-heading">
      <div>
        <h1>{desk ? '服务工作台' : '让每一个问题，有人接续'}</h1>
        <p>{desk ? '沟通、证据与协作，在同一个服务现场。' : '描述设备遇到的问题，我们在同一会话继续处理。'}</p>
      </div>
      <div className="scope-note"><ShieldCheck size={15} aria-hidden="true" />服务记录来自当前账号</div>
    </div>
    <div className="mobile-navigation" aria-label="工作区视图">
      <button type="button" aria-pressed={mobilePanel === 'list'} onClick={() => setMobilePanel('list')}><Inbox size={17} aria-hidden="true" />列表</button>
      <button type="button" aria-pressed={mobilePanel === 'chat'} onClick={() => setMobilePanel('chat')}><MessageSquare size={17} aria-hidden="true" />会话</button>
      <button type="button" aria-pressed={mobilePanel === 'context'} disabled={!selected} onClick={() => setMobilePanel('context')}><FileText size={17} aria-hidden="true" />{desk ? '资料' : '资料与协助'}</button>
    </div>
    <div className={`chat-layout ${selected ? 'has-context' : 'no-context'}`}>
      <ConversationSidebar desk={desk} items={conversations.data} selectedId={selected?.id}
        loading={conversations.isPending} error={conversations.isError ? readableError(conversations.error) : undefined}
        creating={creating} createError={createError} onCreate={() => void startConversation()}
        onSelect={(id) => { setSearchParams({ conversation: id }); setMobilePanel('chat') }} />
      <section className="chat-panel" aria-label="当前会话">
        {selected ? <>
          <div className="chat-heading">
            <div className="chat-identity"><span className="chat-avatar"><Headphones size={22} aria-hidden="true" /></span><div><h2>{desk ? '与客户沟通' : '当前服务会话'}</h2><p>会话 #{selected.id.slice(0, 8)} <span className={`stream-note ${streamState}`}><span className="status-dot" aria-hidden="true" />{streamState === 'connected' ? '实时更新已连接' : streamState === 'connecting' ? '正在连接实时更新' : '重连中，消息仍可查询'}</span></p></div></div>
            <StatusBadge value={selected.status} />
          </div>
          <MessageThread key={selected.id} actor={actor} desk={desk} messages={recorded} pending={visiblePending}
            loading={messages.isPending} error={messages.isError ? readableError(messages.error) : undefined}
            hasMore={Boolean(messages.hasNextPage)} loadingMore={messages.isFetchingNextPage}
            onMore={() => void messages.fetchNextPage()} onRetry={(item) => void deliver(item)} />
          <MessageComposer desk={desk} active={selected.status === 'ACTIVE'} draft={draft} internal={internal}
            onDraft={setDraft} onInternal={setInternal} onSubmit={submitMessage} />
        </> : <div className="message-empty"><h2>{conversations.isPending ? '正在加载会话…' : selectedId ? '会话不可访问' : '选择一个会话'}</h2>
          <p>{conversations.isPending ? '正在查询当前账号的服务记录。' : selectedId ? '请从左侧选择有权限查看的会话。' : desk ? '从左侧打开客户会话。' : '新建会话后即可发送消息。'}</p></div>}
      </section>
      {selected && <aside className="context-panel" aria-label={desk ? '案例与协作信息' : '服务辅助信息'}>
        {desk && <section className="case-summary" aria-label="关联案例摘要">
          <div className="context-heading"><h3><FileText size={17} aria-hidden="true" />关联案例</h3></div>
          {summaries.isPending && <p>正在加载案例…</p>}
          {summaries.isError && <p className="form-error" role="alert">{readableError(summaries.error)}</p>}
          {summaries.data?.length === 0 && <p>当前会话尚未关联案例；可继续查看消息。</p>}
          {summaries.data?.map((summary) => <article key={summary.case.id}>
            <h4>{summary.case.problem_text}</h4>
            <p><StatusBadge value={summary.case.status} /> <span>版本 {summary.case.version}</span></p>
            {summary.device_ids.length > 0 && <div className="device-references">{summary.device_ids.map(id => <Link to={`/devices/${id}`} key={id}>设备档案 #{id.slice(0, 8)}</Link>)}</div>}
            <ul>{summary.facts.map((fact, index) => <li key={`${fact.source}-${index}`}>
              <strong>{fact.label}：</strong>{fact.value} <small>来源：{fact.source} · {fact.verification === 'VERIFIED' ? '已核验' : fact.verification === 'RETRACTED' ? '已撤销' : '待核验'}</small>
            </li>)}</ul>
          </article>)}
        </section>}
        <CollaborationPanel key={selected.id} conversation={selected} actor={actor} desk={desk} />
        <section className="context-ui" aria-label="交互卡">
          {uiDocument.isError && <p className="ui-fallback" role="alert">{readableError(uiDocument.error)}；请继续使用文字消息。</p>}
          <UIDocumentRenderer key={selected.id} document={uiDocument.data ?? null} active={selected.status === 'ACTIVE'}
            recoveryKey={`serviceos:pending-ui:${actor.tenant_id}:${actor.actor_id}:${selected.id}`}
            conversationId={selected.id} conversationVersion={selected.version} desk={desk}
            onCompleted={() => {
              void queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, selected.id) })
              void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected.id) })
            }}
            onRefresh={() => { void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected.id) }) }} />
        </section>
      </aside>}
    </div>
    <div className="workspace-foot"><p>消息与协作状态以服务器记录为准；断线时仍可查询。</p><ConnectionStatus /></div>
  </div>
}
