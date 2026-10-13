import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { type Actor } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'

type StreamState = 'connecting' | 'connected' | 'disconnected'

export function useConversationEvents(actor: Actor, conversationId: string | undefined, desk: boolean): StreamState {
  const queryClient = useQueryClient()
  const [state, setState] = useState<StreamState>('connecting')

  useEffect(() => {
    if (!conversationId) return
    const sequenceKey = `serviceos:event-sequence:${actor.tenant_id}:${actor.actor_id}:${conversationId}`
    let after = '0'
    try { after = localStorage.getItem(sequenceKey) ?? '0' } catch { /* Storage may be disabled. */ }
    const stream = new EventSource(`/api/v1/conversations/${conversationId}/events?after=${encodeURIComponent(after)}`)
    setState('connecting')
    stream.onopen = () => setState('connected')
    stream.onerror = () => setState('disconnected')
    stream.onmessage = (event) => {
      if (/^\d+$/.test(event.lastEventId)) {
        try { localStorage.setItem(sequenceKey, event.lastEventId) } catch { /* The stream still works. */ }
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(actor.tenant_id, actor.actor_id, conversationId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id) })
      if (desk) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.tasks(actor.tenant_id, conversationId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.proposals(actor.tenant_id, conversationId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.summaries(actor.tenant_id, conversationId) })
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.uiDocument(actor.tenant_id, actor.actor_id, conversationId) })
    }
    return () => stream.close()
  }, [actor.tenant_id, actor.actor_id, conversationId, desk, queryClient])

  return state
}
