import type { UIActionBody } from '../../api/client'

// Same-tab recovery only. The server still validates every replay and identity.
const memory = new Map<string, UIActionBody>()
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function valid(value: unknown): value is UIActionBody {
  if (!value || typeof value !== 'object') return false
  const body = value as Partial<UIActionBody>
  return typeof body.client_action_id === 'string' && uuid.test(body.client_action_id) &&
    typeof body.ui_id === 'string' && uuid.test(body.ui_id) &&
    Number.isSafeInteger(body.revision) && body.revision! >= 1 &&
    Number.isSafeInteger(body.expected_conversation_version) && body.expected_conversation_version! >= 1 &&
    body.action_id === 'request-human-assistance' && Boolean(body.input) &&
    Object.keys(body.input!).length === 1 && typeof body.input!.reason === 'string' &&
    body.input!.reason.trim().length >= 3 && body.input!.reason.length <= 1000
}

export function readPendingAction(key: string): UIActionBody | null {
  const cached = memory.get(key)
  if (cached) return cached
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (valid(value)) { memory.set(key, value); return value }
  } catch { /* Disabled or invalid storage must not prevent the text interface. */ }
  return null
}

export function savePendingAction(key: string, body: UIActionBody | null) {
  if (body) memory.set(key, body)
  else memory.delete(key)
  try {
    if (body) sessionStorage.setItem(key, JSON.stringify(body))
    else sessionStorage.removeItem(key)
  } catch { /* In-memory recovery still covers conversation and route changes. */ }
}

export function clearPendingAction(key: string, clientActionId: string) {
  if (readPendingAction(key)?.client_action_id === clientActionId) savePendingAction(key, null)
}
