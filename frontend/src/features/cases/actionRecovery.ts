import type { components } from '../../api/schema'

type ActionBody = components['schemas']['MockActionRequest']
type DecisionBody = components['schemas']['ActionApprovalDecision']
export type PendingDecision = { approvalId: string, body: DecisionBody }

const memory = new Map<string, unknown>()
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function read<T>(key: string, valid: (value: unknown) => value is T): T | null {
  const cached = memory.get(key)
  if (valid(cached)) return cached
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    if (valid(parsed)) { memory.set(key, parsed); return parsed }
  } catch { /* Private browsing may disable storage; memory still covers navigation. */ }
  return null
}

function save(key: string, value: unknown | null) {
  if (value === null) memory.delete(key)
  else memory.set(key, value)
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, JSON.stringify(value))
  } catch { /* Same-tab memory remains usable. */ }
}

function validAction(value: unknown): value is ActionBody {
  if (!value || typeof value !== 'object') return false
  const body = value as Partial<ActionBody>
  return typeof body.client_action_id === 'string' && uuid.test(body.client_action_id) &&
    Number.isSafeInteger(body.expected_case_version) && body.expected_case_version! >= 1 &&
    body.action_kind === 'MOCK_SERVICE_REQUEST' &&
    typeof body.reason === 'string' && body.reason.trim().length >= 3 && body.reason.length <= 1000
}

function validDecision(value: unknown): value is PendingDecision {
  if (!value || typeof value !== 'object') return false
  const pending = value as Partial<PendingDecision>
  if (typeof pending.approvalId !== 'string' || !uuid.test(pending.approvalId)) return false
  const body = pending.body
  return Boolean(body) && typeof body!.decision_id === 'string' && uuid.test(body!.decision_id) &&
    Number.isSafeInteger(body!.expected_version) && body!.expected_version >= 1 &&
    ['APPROVED', 'REJECTED'].includes(body!.decision) &&
    typeof body!.reason === 'string' && body!.reason.trim().length >= 3 && body!.reason.length <= 1000
}

export const readPendingMockAction = (key: string) => read(key, validAction)
export const savePendingMockAction = (key: string, value: ActionBody | null) => save(key, value)
export const readPendingMockDecision = (key: string) => read(key, validDecision)
export const savePendingMockDecision = (key: string, value: PendingDecision | null) => save(key, value)
