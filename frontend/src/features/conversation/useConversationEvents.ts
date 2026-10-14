import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, type Actor } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'

type StreamState = 'connecting' | 'connected' | 'disconnected'
const stages = ['RUNNING', 'LOOKUP', 'WAITING_EVIDENCE', 'WAITING_APPROVAL', 'COMPLETED', 'FAILED'] as const
export type AgentProgress = {
  conversationId: string
  runId: string
  stage: typeof stages[number]
  summary: string
  sequence: number
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

// Canonical, non-negative safe integers only: no rounding, exponent notation or Infinity.
function cursor(value: unknown): number | null {
  if (typeof value === 'string' && !/^(0|[1-9]\d*)$/.test(value)) return null
  if (typeof value !== 'string' && typeof value !== 'number') return null
  const number = Number(value)
  return Number.isSafeInteger(number) && number >= 0 ? number : null
}

function visibleEvent(value: unknown, conversationId: string, desk: boolean) {
  if (!record(value) || value.conversation_id !== conversationId ||
    typeof value.sequence !== 'number' || cursor(value.sequence) === null || value.sequence < 1 ||
    typeof value.type !== 'string' || !record(value.data) ||
    !(value.visibility === 'PUBLIC' || (desk && value.visibility === 'INTERNAL'))) return null
  return { sequence: value.sequence, type: value.type, data: value.data }
}

export function useConversationEvents(actor: Actor, conversationId: string | undefined, desk: boolean,
  onProgress?: (progress: AgentProgress | null) => void): StreamState {
  const queryClient = useQueryClient()
  const scope = `${actor.tenant_id}:${actor.actor_id}:${conversationId ?? ''}:${desk}`
  const [connection, setConnection] = useState({ scope, state: 'connecting' as StreamState })

  useEffect(() => {
    onProgress?.(null)
    if (!conversationId) return
    let disposed = false
    let historyRequest: AbortController | undefined
    let progressSequence = 0
    const sequenceKey = `serviceos:event-sequence:${actor.tenant_id}:${actor.actor_id}:${conversationId}`
    let after = 0
    try { after = cursor(localStorage.getItem(sequenceKey)) ?? 0 } catch { /* Storage is optional. */ }
    const updateState = (state: StreamState) => { if (!disposed) setConnection({ scope, state }) }
    const refreshSnapshots = () => {
      if (disposed) return
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(actor.tenant_id, actor.actor_id, conversationId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      // Related cases use the same authorized case cache as the case detail page.
      void queryClient.invalidateQueries({ queryKey: ['case', actor.tenant_id, actor.actor_id] })
      if (desk) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, conversationId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.proposals(actor.tenant_id, conversationId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.summaries(actor.tenant_id, conversationId) })
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, conversationId) })
    }
    const acceptProgress = (event: NonNullable<ReturnType<typeof visibleEvent>>) => {
      if (disposed || event.type !== 'agent.progress' || event.sequence <= progressSequence) return
      const { run_id, stage, summary } = event.data
      if (typeof run_id !== 'string' || !run_id || run_id.length > 100 ||
        typeof stage !== 'string' || !stages.includes(stage as AgentProgress['stage']) ||
        typeof summary !== 'string' || !summary.trim() || summary.length > 1000) return
      progressSequence = event.sequence
      onProgress?.({ conversationId, runId: run_id, stage: stage as AgentProgress['stage'], summary, sequence: event.sequence })
    }
    const reconcileProgress = async () => {
      historyRequest?.abort()
      const request = new AbortController()
      historyRequest = request
      // Ascending history is the existing API. It restores progress even when the saved
      // SSE cursor is already at the tail. History never advances the transport cursor.
      let historyAfter = 0
      try {
        while (!disposed && !request.signal.aborted) {
          const { data, response } = await api.GET('/api/v1/conversations/{id}/event-history', {
            params: { path: { id: conversationId }, query: { after: historyAfter, limit: 100 } },
            signal: request.signal,
          })
          if (disposed || request.signal.aborted || !response.ok || !data || !Array.isArray(data.items)) return
          for (const item of data.items) {
            const event = visibleEvent(item, conversationId, desk)
            if (event) acceptProgress(event)
          }
          const next = cursor(data.next_after)
          if (data.items.length < 100 || next === null || next <= historyAfter) return
          historyAfter = next
        }
      } catch { /* Snapshot polling and SSE remain available when history fails. */ }
    }
    updateState('connecting')
    const stream = new EventSource(`/api/v1/conversations/${encodeURIComponent(conversationId)}/events?after=${after}`)
    stream.onopen = () => {
      if (disposed) return
      updateState('connected')
      refreshSnapshots()
      void reconcileProgress()
    }
    stream.onerror = () => {
      if (disposed) return
      updateState('disconnected')
      // Do not recreate EventSource: native reconnect carries the server's Last-Event-ID.
      refreshSnapshots()
    }
    stream.onmessage = (message) => {
      if (disposed) return
      const sequence = cursor(message.lastEventId)
      if (sequence === null || sequence <= after) return
      let value: unknown
      try { value = JSON.parse(message.data) } catch { return }
      const event = visibleEvent(value, conversationId, desk)
      if (!event || event.sequence !== sequence) return
      // Visibility filtering legitimately leaves holes; a gap is not evidence of loss.
      after = sequence
      try { localStorage.setItem(sequenceKey, String(after)) } catch { /* Keep the in-memory cursor. */ }
      acceptProgress(event)
      refreshSnapshots()
    }
    return () => {
      disposed = true
      historyRequest?.abort()
      stream.onopen = null
      stream.onerror = null
      stream.onmessage = null
      stream.close()
    }
  }, [actor.tenant_id, actor.actor_id, conversationId, desk, queryClient, scope, onProgress])

  return connection.scope === scope ? connection.state : 'connecting'
}
