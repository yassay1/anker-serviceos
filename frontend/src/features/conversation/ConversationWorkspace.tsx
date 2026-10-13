import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  type Actor, type SendBody, createConversation, listConversations,
  listDeskCaseSummaries, listMessages, refreshUIDocument, sendMessage,
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
  const [draft, setDraft] = useState('')
  const [internal, setInternal] = useState(false)
  const [pending, setPending] = useState<Pending[]>([])
  const conversations = useQuery({
    queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations,
    refetchInterval: 10_000,
  })
  const selectedId = searchParams.get('conversation')
  const selected = conversations.data?.find((item) => item.id === selectedId) ?? (
    selectedId ? undefined : conversations.data?.[0]
  )
  const streamState = useConversationEvents(actor, selected?.id, desk)
  const messageQueryKey = queryKeys.messages(actor.tenant_id, actor.actor_id, selected?.id ?? '')
  const messages = useInfiniteQuery({
    queryKey: messageQueryKey,
    queryFn: ({ pageParam }) => listMessages(selected!.id, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(selected),
    refetchInterval: streamState === 'connected' ? false : 4_000,
  })
  const summaries = useQuery({
    queryKey: queryKeys.summaries(actor.tenant_id, selected?.id ?? ''),
    queryFn: () => listDeskCaseSummaries(selected!.id),
    enabled: desk && Boolean(selected),
  })
  const uiDocument = useQuery({
    queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected?.id ?? ''),
    queryFn: () => refreshUIDocument(selected!.id),
    enabled: Boolean(selected),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
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

  return <div className={`workspace-page ${desk ? 'desk-view' : 'support-view'}`}>
    <div className="page-heading">
      <div>
        <span className="section-kicker">{desk ? '客服工作区' : '用户服务'}</span>
        <h1>{desk ? '持续处理每个服务问题' : '我们从你的问题开始'}</h1>
        <p>{desk ? '在同一工作区查看沟通、案例事实和待处理事项。' : '描述遇到的问题，消息和服务记录会保存在同一会话中。'}</p>
      </div>
      <div className="page-status"><span className="status-dot" aria-hidden="true" />服务记录来自当前账号</div>
    </div>
    <div className={`chat-layout ${selected ? 'has-context' : 'no-context'}`}>
      <ConversationSidebar desk={desk} items={conversations.data} selectedId={selected?.id}
        loading={conversations.isPending} error={conversations.isError ? readableError(conversations.error) : undefined}
        creating={creating} createError={createError} onCreate={() => void startConversation()}
        onSelect={(id) => setSearchParams({ conversation: id })} />
      <section className="chat-panel" aria-label="当前会话">
        {selected ? <>
          <div className="chat-heading">
            <div><span className="section-kicker">会话 {selected.id.slice(0, 8)}</span>
              <h2>{desk ? '与客户沟通' : '当前服务会话'}</h2>
              <p>{streamState === 'connected' ? '实时更新已连接' : streamState === 'connecting' ? '正在连接实时更新' : '实时更新断开，正在重连；消息仍可查询'}</p></div>
            <span className="state-pill">{selected.status === 'ACTIVE' ? '进行中' : '已归档'}</span>
          </div>
          <MessageThread actor={actor} desk={desk} messages={recorded} pending={visiblePending}
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
          <div className="context-heading"><span className="section-kicker">服务背景</span><h3>关联案例</h3></div>
          {summaries.isPending && <p>正在加载案例…</p>}
          {summaries.isError && <p className="form-error" role="alert">{readableError(summaries.error)}</p>}
          {summaries.data?.length === 0 && <p>当前会话尚未关联案例；可继续查看消息。</p>}
          {summaries.data?.map((summary) => <article key={summary.case.id}>
            <h4>{summary.case.problem_text}</h4>
            <p>状态：{summary.case.status} · 版本：{summary.case.version} · 关联设备：{summary.device_ids.length}</p>
            <ul>{summary.facts.map((fact, index) => <li key={`${fact.source}-${index}`}>
              <strong>{fact.label}：</strong>{fact.value} <small>来源：{fact.source} · {fact.verification === 'VERIFIED' ? '已核验' : fact.verification === 'RETRACTED' ? '已撤销' : '待核验'}</small>
            </li>)}</ul>
          </article>)}
        </section>}
        <CollaborationPanel key={selected.id} conversation={selected} actor={actor} desk={desk} />
        <section className="context-ui" aria-label="交互卡">
          {uiDocument.isError && <p className="ui-fallback" role="alert">{readableError(uiDocument.error)}；请继续使用文字消息。</p>}
          <UIDocumentRenderer key={`${selected.id}-${uiDocument.data?.revision ?? 0}`} document={uiDocument.data ?? null}
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
