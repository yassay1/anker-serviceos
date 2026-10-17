import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { FileText, Headphones, Inbox, MessageSquare, ShieldCheck, Sparkles, ChevronDown, Plus } from 'lucide-react'
import {
  ApiFailure, type Actor, type SendBody, createConversation, listConversations, listCustomerCaseLinks, listDevices,
  listDeskCaseSummaries, listMessages, readUIDocument, refreshUIDocument, sendMessage,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { ConnectionStatus } from '../../shared/ConnectionStatus'
import { UIDocumentRenderer } from '../ui-document/UIDocumentRenderer'
import { type AgentProgress, type SpecialistActivity, useConversationEvents } from './useConversationEvents'
import { ConversationSidebar, type ConversationPreview } from './ConversationSidebar'
import { MessageThread } from './MessageThread'
import { MessageComposer } from './MessageComposer'
import { ConversationAttachments } from './ConversationAttachments'
import { AgentProgressNote, SpecialistActivityNote } from './ConversationContext'
import { StatusBadge, statusLabel } from '../../shared/StatusBadge'
import { StaffConversationContext } from './StaffConversationContext'
import { CustomerAssistanceStatus } from './CustomerAssistanceStatus'
import { CustomerAvatar, customerLabel } from '../../shared/StaffUI'
import { DeviceIcon } from '../../shared/DeviceIcon'
import { StaffTaskQueue } from '../collaboration/StaffTaskQueue'

type Pending = {
  conversationId: string
  body: SendBody
  status: 'sending' | 'uncertain' | 'saved'
  error?: string
}

export function ConversationWorkspace({ actor, desk }: { actor: Actor, desk: boolean }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)
  const [previews, setPreviews] = useState<Record<string, ConversationPreview>>({})
  const [drafts, setDrafts] = useState<Record<string, { text: string, internal: boolean }>>({})
  const [mobilePanel, setMobilePanel] = useState<'list' | 'chat' | 'context' | 'details' | 'devices'>(() =>
    desk && typeof window !== 'undefined' && window.matchMedia('(max-width: 1000px)').matches ? 'list' : 'chat')
  const [wideScreen, setWideScreen] = useState(() => typeof window !== 'undefined' && window.matchMedia('(min-width: 1001px)').matches)
  const [compactDesk, setCompactDesk] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 1180px)').matches)
  const [pending, setPending] = useState<Pending[]>([])
  const selectorRef = useRef<HTMLDetailsElement>(null)
  const quickReplyLocks = useRef(new Set<string>())
  const [quickReplyError, setQuickReplyError] = useState('')
  const [attachmentsFor, setAttachmentsFor] = useState<string | null>(null)
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1001px)')
    const update = () => setWideScreen(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1180px)')
    const update = () => setCompactDesk(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  const conversations = useQuery({
    queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations,
    refetchInterval: 10_000,
  })
  const selectedId = searchParams.get('conversation')
  const selectionKey = `serviceos:last-conversation:${actor.tenant_id}:${actor.actor_id}:${desk ? 'desk' : 'customer'}`
  const rememberedId = (() => {
    try { return localStorage.getItem(selectionKey) } catch { return null }
  })()
  const selected = conversations.data?.find((item) => item.id === selectedId) ?? (
    selectedId ? undefined : conversations.data?.find(item => item.id === rememberedId) ?? conversations.data?.[0]
  )
  useEffect(() => {
    if (!selected) return
    try { localStorage.setItem(selectionKey, selected.id) } catch { /* Server history does not depend on browser storage. */ }
    if (!selectedId) setSearchParams({ conversation: selected.id }, { replace: true })
  }, [selected?.id, selectionKey, selectedId, setSearchParams])
  const draft = selected ? drafts[selected.id]?.text ?? '' : ''
  const internal = selected ? drafts[selected.id]?.internal ?? false : false
  useEffect(() => {
    const entry = location.state as { draft?: unknown } | null
    if (desk || !selected || typeof entry?.draft !== 'string') return
    const text = entry.draft.slice(0, 8000)
    setDrafts(current => current[selected.id]?.text ? current : { ...current, [selected.id]: { text, internal: false } })
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [desk, selected?.id, location.state, location.pathname, location.search, navigate])
  function setDraft(text: string) {
    if (selected) setDrafts(current => ({ ...current, [selected.id]: { text, internal: current[selected.id]?.internal ?? false } }))
  }
  function setInternal(value: boolean) {
    if (selected) setDrafts(current => ({ ...current, [selected.id]: { text: current[selected.id]?.text ?? '', internal: value } }))
  }
  const [progress, setProgress] = useState<AgentProgress | null>(null)
  const [specialistActivity, setSpecialistActivity] = useState<SpecialistActivity | null>(null)
  const streamState = useConversationEvents(actor, selected?.id, desk, setProgress, setSpecialistActivity)
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
  const customerCaseLinks = useQuery({
    queryKey: queryKeys.customerCaseLinks(actor.tenant_id, actor.actor_id, selected?.id ?? ''),
    queryFn: () => listCustomerCaseLinks(selected!.id), enabled: !desk && Boolean(selected),
    refetchInterval: query => query.state.status === 'error' ? false : 10_000,
  })
  const customerDevices = useQuery({
    queryKey: queryKeys.devices(actor.tenant_id, actor.actor_id), queryFn: listDevices,
    enabled: !desk && Boolean(selected),
  })
  const uiDocument = useQuery({
    queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected?.id ?? ''),
    queryFn: () => selected!.status === 'ACTIVE' ? refreshUIDocument(selected!.id) : readUIDocument(selected!.id),
    enabled: Boolean(selected),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchInterval: 10_000,
  })
  const soleCase = desk && summaries.data?.length === 1 ? summaries.data[0] : undefined
  const recorded = useMemo(() => [...new Map((messages.data?.pages.flatMap((page) => page.items) ?? [])
    .map(message => [message.id, message])).values()], [messages.data])
  const visiblePending = useMemo(() => {
    const recordedKeys = new Set(recorded.map(message => message.client_message_id))
    return pending.filter(item => item.conversationId === selected?.id && !recordedKeys.has(item.body.client_message_id))
  }, [recorded, pending, selected?.id])
  const relatedCaseIds = [...new Set(recorded.flatMap(message => message.related_case_id ? [message.related_case_id] : []))]
  const linkedDeviceIds = new Set(customerCaseLinks.data?.flatMap(item => item.device_ids) ?? [])
  const linkedDevices = customerDevices.data?.filter(device => linkedDeviceIds.has(device.id)) ?? []
  const lastPublic = recorded.filter(message => message.visibility === 'PUBLIC').at(-1)
  useEffect(() => {
    if (!desk || !selected || !lastPublic || messages.hasNextPage || messages.isFetching || messages.isError) return
    const preview = { id: lastPublic.id, created_at: lastPublic.created_at,
      text: lastPublic.content.map(part => part.text).filter(Boolean).join(' ').slice(0, 180) || '[附件消息]' }
    setPreviews(current => current[selected.id]?.id === preview.id ? current : { ...current, [selected.id]: preview })
  }, [desk, selected?.id, lastPublic, messages.hasNextPage, messages.isFetching, messages.isError])
  const generating = Boolean(progress && selected && progress.conversationId === selected.id && !['COMPLETED', 'FAILED'].includes(progress.stage) &&
    !recorded.some(message => message.author_kind === 'AGENT' && message.client_message_id === progress.runId))
  const quickReplyMessageId = !desk && selected?.status === 'ACTIVE' && selected.collaboration_mode === 'AI_LEAD' &&
    selected.reply_policy === 'AI_AUTO' && visiblePending.length === 0 && !generating && !messages.hasNextPage && !messages.isError &&
    lastPublic?.author_kind === 'AGENT' && !quickReplyLocks.current.has(`${selected.id}:${lastPublic.id}`) ? lastPublic.id : undefined

  async function startConversation() {
    setCreating(true)
    setCreateError('')
    try {
      const created = await createConversation()
      await queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      setSearchParams({ conversation: created.id })
      if (!desk && !wideScreen && selectorRef.current) selectorRef.current.open = false
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      return true
    } catch (failure) {
      if (item.body.reply_to_message_id && failure instanceof ApiFailure && failure.status >= 400 && failure.status < 500) {
        setPending(current => current.filter(part => part.body.client_message_id !== item.body.client_message_id))
        setQuickReplyError(readableError(failure))
        void queryClient.invalidateQueries({ queryKey: queryKeys.messages(actor.tenant_id, actor.actor_id, item.conversationId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
        return false
      }
      setPending((current) => current.map((part) => part.body.client_message_id === item.body.client_message_id
        ? { ...part, status: 'uncertain', error: readableError(failure) } : part))
      return false
    }
  }

  function submitChoice(label: string, sourceMessageId?: string, caseId: string | null = null): Promise<boolean> {
    if (!selected || desk || selected.status !== 'ACTIVE') return Promise.resolve(false)
    if (sourceMessageId) {
      const lockKey = `${selected.id}:${sourceMessageId}`
      if (sourceMessageId !== quickReplyMessageId || quickReplyLocks.current.has(lockKey)) return Promise.resolve(false)
      quickReplyLocks.current.add(lockKey)
    }
    setQuickReplyError('')
    const item: Pending = {
      conversationId: selected.id,
      body: {
        client_message_id: crypto.randomUUID(),
        ...(sourceMessageId ? { reply_to_message_id: sourceMessageId } : {}),
        content: [{ type: 'text', text: label }],
        related_case_id: caseId,
        visibility: 'PUBLIC',
      },
      status: 'sending',
    }
    setPending((current) => [...current, item])
    return deliver(item)
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

  const interactionCards = selected && <section id="conversation-interactions" tabIndex={-1}
    className={`context-ui ${desk ? '' : 'conversation-ui'}`} aria-label="交互卡">
    {uiDocument.isError && <div className="ui-load-error"><p className="ui-fallback" role="alert">{readableError(uiDocument.error)}；请继续使用文字消息。</p>
      <button type="button" onClick={() => void uiDocument.refetch()}>重试交互卡</button></div>}
    <UIDocumentRenderer key={selected.id} document={uiDocument.isError ? null : uiDocument.data ?? null}
      loading={uiDocument.isPending} active={selected.status === 'ACTIVE' && !uiDocument.isError}
      recoveryKey={`serviceos:pending-ui:${actor.tenant_id}:${actor.actor_id}:${selected.id}`}
      conversationId={selected.id} conversationVersion={selected.version} desk={desk}
      onReply={() => document.getElementById('message-draft')?.focus()}
      onChoose={submitChoice}
      onCompleted={() => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, selected.id) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected.id) })
      }}
      onRefresh={() => { void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected.id) }) }} />
  </section>

  const conversationList = <ConversationSidebar desk={desk} previews={previews} items={conversations.data} selectedId={selected?.id}
    loading={conversations.isPending} error={conversations.isError ? readableError(conversations.error) : undefined}
    creating={creating} createError={createError} onCreate={() => void startConversation()} showCreate={false}
    onSelect={(id) => { if (!desk && !wideScreen && selectorRef.current) selectorRef.current.open = false; setSearchParams({ conversation: id }); setMobilePanel('chat') }} />

  return <div className={`workspace-page ${desk ? 'desk-view' : 'support-view'} mobile-${mobilePanel}`}>
    <div className="page-heading">
      <div>
        <h1>{desk ? '服务工作台' : '对话'}</h1>
        <p>{desk ? '沟通、证据与协作，在同一个服务现场。' : '继续已有服务，或开始一个新问题。'}</p>
      </div>
      {desk ? <div className="scope-note"><ShieldCheck size={15} aria-hidden="true" />服务记录来自当前账号</div> :
        <div className="customer-workspace-actions"><Link to="/" className="customer-history-link">服务首页</Link><button type="button" className="primary-button customer-new-conversation" disabled={creating} onClick={() => void startConversation()}>
          <Plus size={18} aria-hidden="true" />{creating ? '正在建立会话…' : '开始新对话'}
        </button></div>}
    </div>
    <nav className="mobile-navigation" aria-label={desk ? '客服工作区视图' : '服务视图'}>
      {desk ? <>
        <button type="button" aria-pressed={mobilePanel === 'list'} onClick={() => setMobilePanel('list')}><Inbox size={17} aria-hidden="true" />处理队列</button>
        <button type="button" aria-pressed={mobilePanel === 'chat'} onClick={() => setMobilePanel('chat')}><MessageSquare size={17} aria-hidden="true" />客户会话</button>
        <button type="button" aria-pressed={mobilePanel === 'context'} disabled={!selected} onClick={() => setMobilePanel('context')}><FileText size={17} aria-hidden="true" />服务资料</button>
      </> : <>
        <button type="button" aria-pressed={mobilePanel === 'chat'} onClick={() => setMobilePanel('chat')}><MessageSquare size={17} aria-hidden="true" />对话</button>
        <button type="button" aria-pressed={mobilePanel === 'details'} disabled={!selected} onClick={() => setMobilePanel('details')}><FileText size={17} aria-hidden="true" />处理详情</button>
        <button type="button" aria-pressed={mobilePanel === 'devices'} disabled={!selected} onClick={() => setMobilePanel('devices')}><Headphones size={17} aria-hidden="true" />关联设备</button>
      </>}
    </nav>
    <div className={`chat-layout ${selected ? 'has-context' : 'no-context'}`}>
      <div className="conversation-selector">{desk ? <>{compactDesk && <StaffTaskQueue actor={actor} onOpenConversation={() => setMobilePanel('chat')} />}{(!compactDesk || wideScreen) && conversationList}</> : <details ref={selectorRef} open={mobilePanel === 'list' || wideScreen}><summary><Inbox size={16} />历史问答 · 点击切换会话<span>{conversations.data?.length ?? 0}</span><ChevronDown size={15} /></summary>{conversationList}</details>}</div>
      <section className="chat-panel" aria-label="当前会话">
        {selected ? <>
          <div className="chat-heading">
            <div className="chat-identity">{desk ? <CustomerAvatar id={selected.customer_id} /> : <span className="chat-avatar"><Headphones size={22} aria-hidden="true" /></span>}<div><h2>{desk ? customerLabel(selected.customer_id) : soleCase ? soleCase.case.problem_text : selected.title || '新会话'}</h2>{desk && <p className="chat-problem-title">{soleCase?.case.problem_text || selected.title}</p>}<p>{!desk && `会话 #${selected.id.slice(0, 8)} · ${statusLabel(selected.status)} `}<span className={`stream-note ${streamState}`}><span className="status-dot" aria-hidden="true" />{streamState === 'connected' ? '实时更新已连接' : streamState === 'connecting' ? '正在连接实时更新' : '重连中，消息仍可查询'}</span></p></div></div>
            <StatusBadge value={!desk && soleCase ? soleCase.case.status : selected.status} />
          </div>
          <MessageThread key={`thread:${selected.id}`} actor={actor} desk={desk} messages={recorded} pending={visiblePending}
            quickReplyMessageId={quickReplyMessageId} onQuickReply={submitChoice}
            loading={messages.isPending} error={messages.isError ? readableError(messages.error) : undefined}
            hasMore={Boolean(messages.hasNextPage)} loadingMore={messages.isFetchingNextPage}
            onMore={() => void messages.fetchNextPage()} onRetry={(item) => void deliver(item)}>
            {quickReplyError && <p className="form-error" role="alert">{quickReplyError}</p>}
            {!desk && selected.status === 'ACTIVE' && selected.collaboration_mode === 'AI_LEAD' &&
              selected.reply_policy === 'AI_AUTO' && !messages.hasNextPage && !messages.isError &&
              lastPublic?.author_kind === 'CUSTOMER' && progress?.conversationId !== selected.id &&
              <p className="agent-progress" role="status">消息已保存。</p>}
            {progress?.conversationId === selected.id && (desk || ['WAITING_EVIDENCE', 'FAILED'].includes(progress.stage)) &&
              <AgentProgressNote progress={progress} connected={streamState === 'connected'} />}
            {desk && specialistActivity?.conversationId === selected.id && <SpecialistActivityNote activity={specialistActivity} connected={streamState === 'connected'} />}
            {!desk && interactionCards}
          </MessageThread>
          <MessageComposer key={`composer:${selected.id}`} desk={desk} active={selected.status === 'ACTIVE'} draft={draft} internal={internal}
            onDraft={setDraft} onInternal={setInternal} onSubmit={submitMessage} onAttach={() => setAttachmentsFor(selected.id)} />
          {attachmentsFor === selected.id && selected.status === 'ACTIVE' && <ConversationAttachments key={`attachments:${selected.id}`}
            actor={actor} conversationId={selected.id} customerId={selected.customer_id} relatedCaseIds={relatedCaseIds}
            initialProblem={recorded.find(message => message.author_kind === 'CUSTOMER' && message.visibility === 'PUBLIC')?.content.map(part => part.text).join('\n') ?? draft}
            onClose={() => setAttachmentsFor(null)} />}
          {!desk && relatedCaseIds.length > 0 && <div className="conversation-evidence-links">{relatedCaseIds.map(id =>
            <Link key={id} to={`/cases/${id}#case-evidence`}>上传图片／查看案例 #{id.slice(0, 8)}</Link>)}</div>}
        </> : <div className="message-empty"><span className="empty-symbol"><Sparkles size={28} aria-hidden="true" /></span><h2>{conversations.isPending ? '正在加载会话…' : selectedId ? '会话不可访问' : '让我们一起找到问题所在'}</h2>
          <p>{conversations.isPending ? '正在查询当前账号的服务记录。' : selectedId ? '请从左侧选择有权限查看的会话。' : desk ? '从左侧打开客户会话。' : '告诉我们设备型号、遇到的现象和已尝试的方法。'}</p>{!desk && !conversations.isPending && <button type="button" className="primary-button" disabled={creating} onClick={() => void startConversation()}><Sparkles size={17} />{creating ? '正在建立会话…' : '开始新的诊断'}</button>}{createError && <p role="alert" className="form-error">{createError}</p>}</div>}
      </section>
      {selected && desk && <StaffConversationContext key={`context:${selected.id}`} actor={actor} conversation={selected} summaries={summaries.data} messages={recorded}
        summaryError={summaries.isError ? readableError(summaries.error) : undefined} loading={summaries.isPending} interactions={interactionCards}
        onPhotoDraft={() => { setInternal(false); const text = '为了进一步核对问题，请补充设备外观、接口及型号标签的清晰照片，并说明出现问题时的具体情况。'; setDraft((draft ? `${draft}\n${text}` : text).slice(0, 8000)); document.getElementById('message-draft')?.focus() }} />}
      {selected && !desk && <aside className="context-panel customer-service-context" aria-label="服务资料">
        <div className="assistant-panel-heading"><Sparkles size={21} /><h2>本次服务</h2></div>
        <section className="customer-context-section customer-context-details" aria-labelledby="customer-details-title">
          <h3 id="customer-details-title">处理详情</h3>
          {customerCaseLinks.isPending && <p role="status">正在读取关联服务记录…</p>}
          {customerCaseLinks.isError && <div className="form-error" role="alert"><p>{readableError(customerCaseLinks.error)}</p><button type="button" onClick={() => void customerCaseLinks.refetch()}>重试</button></div>}
          {customerCaseLinks.isSuccess && customerCaseLinks.data.length === 0 && <p className="empty-note">当前会话尚无关联服务记录；可继续对话，不需要先创建案例。</p>}
          {customerCaseLinks.data?.map(({ case: serviceCase }) => <article className="customer-linked-case" key={serviceCase.id}>
            <div className="customer-linked-case-heading"><StatusBadge value={serviceCase.status} /><span>案例 #{serviceCase.id.slice(0, 8)}</span></div>
            <h4><Link to={`/cases/${serviceCase.id}`}>{serviceCase.problem_text}</Link></h4>
            <p>{serviceCase.user_goal || '服务目标尚未补充。'}</p>
            <Link className="customer-context-link" to={`/cases/${serviceCase.id}`}>查看证据、动作与核验记录</Link>
          </article>)}
        </section>
        <section className="customer-context-section customer-context-devices" aria-labelledby="customer-devices-title">
          <h3 id="customer-devices-title">关联设备</h3>
          {customerDevices.isPending && <p role="status">正在读取设备档案…</p>}
          {customerDevices.isError && <div className="form-error" role="alert"><p>{readableError(customerDevices.error)}</p><button type="button" onClick={() => void customerDevices.refetch()}>重试</button></div>}
          {customerCaseLinks.isError && <p className="muted">无法确认此会话关联的设备。</p>}
          {customerCaseLinks.isSuccess && customerCaseLinks.data.length > 0 && linkedDeviceIds.size === 0 && <p className="empty-note">关联案例尚无设备档案。设备身份未知时可以继续服务。</p>}
          {customerCaseLinks.isSuccess && customerCaseLinks.data.length === 0 && <p className="empty-note">没有关联案例，因此当前没有关联设备。</p>}
          <div className="customer-linked-devices">{linkedDevices.map(device => <article className="customer-linked-device" key={device.id}>
            <DeviceIcon model={device.model} size={25} aria-hidden="true" />
            <div><strong>{device.model || '型号待确认'}</strong><StatusBadge value={device.identity_status} />
              {device.verified_facts?.length ? <ul>{device.verified_facts.map(fact => <li key={fact.id}>{fact.fact_key}：{typeof fact.value === 'string' ? fact.value : JSON.stringify(fact.value)}</li>)}</ul> : <small>暂无已核验设备事实</small>}
            </div>
            <Link to={`/devices/${device.id}`} aria-label={`查看设备档案 ${device.model || '型号待确认'}`}>查看</Link>
          </article>)}</div>
        </section>
        <section className="collaboration-panel customer-assistance customer-context-assistance customer-context-details" aria-label="服务协助">
            <h3><Headphones size={18} aria-hidden="true" />需要进一步协助？</h3>
            <p>如需人工协助，可提交请求；服务记录会保留在当前会话。</p>
            <CustomerAssistanceStatus actor={actor} conversationId={selected.id} />
            <UIDocumentRenderer key={`assistance:${selected.id}`} document={uiDocument.isError ? null : uiDocument.data ?? null}
              loading={uiDocument.isPending} active={selected.status === 'ACTIVE' && !uiDocument.isError}
              recoveryKey={`serviceos:pending-ui:${actor.tenant_id}:${actor.actor_id}:${selected.id}`}
              conversationId={selected.id} conversationVersion={selected.version} desk={false} placement="assistance"
              onCompleted={() => {
                void queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, selected.id) })
                void queryClient.invalidateQueries({ queryKey: queryKeys.customerAssistance(actor.tenant_id, actor.actor_id, selected.id) })
                void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected.id) })
              }}
              onRefresh={() => { void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, selected.id) }) }} />
        </section>
      </aside>}
    </div>
    <div className="workspace-foot"><p>消息与协作状态以服务器记录为准；断线时仍可查询。</p><ConnectionStatus /></div>
  </div>
}
