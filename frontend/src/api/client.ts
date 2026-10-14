import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export type Actor = components['schemas']['ActorRead']
export type Conversation = components['schemas']['ConversationRead']
export type Message = components['schemas']['MessageRead']
export type MessagePage = components['schemas']['MessagePage']
export type MessageReceipt = components['schemas']['MessageReceipt']
export type SendBody = components['schemas']['SendMessage']
export type DeskCaseSummary = components['schemas']['DeskCaseSummary']
export type Task = components['schemas']['TaskRead']
export type Proposal = components['schemas']['ProposalRead']
export type UIDocument = components['schemas']['UIDocumentRead']
export type UIActionBody = components['schemas']['UIActionRequest']
export type Device = components['schemas']['DeviceRead']
export type ServiceCase = components['schemas']['CaseRead']
export type CaseAction = components['schemas']['CaseActionRead']
export type ActionApproval = components['schemas']['ActionApprovalRead']
export type CaseImageEvidence = components['schemas']['EvidenceRead']
export type EvidencePage = components['schemas']['EvidencePage']
export type ResolutionContract = components['schemas']['ResolutionContractRead']
export type Verification = components['schemas']['VerificationRead']

export const api = createClient<paths>({ baseUrl: '/', credentials: 'same-origin' })

export class ApiFailure extends Error {
  constructor(public status: number, message: string) { super(message) }
}

function requireData<T>(data: T | undefined, error: unknown, response: Response, fallback: string): T {
  if (!response.ok || data === undefined) {
    const detail = error && typeof error === 'object' && 'detail' in error ? (error as { detail: unknown }).detail : null
    throw new ApiFailure(response.status, typeof detail === 'string' ? detail : fallback)
  }
  return data
}

export async function readHealth(signal?: AbortSignal) {
  const { data, error, response } = await api.GET('/api/v1/health', {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5_000)]) : AbortSignal.timeout(5_000),
  })
  return requireData(data, error, response, '本地服务未响应，请启动服务后重新检查。')
}

export async function readActor(): Promise<Actor | null> {
  const { data, error, response } = await api.GET('/api/v1/auth/me', { signal: AbortSignal.timeout(5_000) })
  if (response.status === 401) return null
  return requireData(data, error, response, '登录状态暂时无法确认。')
}

export async function loginLocal(username: string, password: string): Promise<Actor> {
  const { data, error, response } = await api.POST('/api/v1/local-auth/login', {
    body: { username, password }, signal: AbortSignal.timeout(10_000),
  })
  return requireData(data, error, response, '登录失败，请检查账号与密码。')
}

export async function logout(): Promise<void> {
  const { response, error } = await api.POST('/api/v1/auth/logout')
  if (!response.ok) requireData(undefined, error, response, '退出登录失败。')
}

export async function listConversations(): Promise<Conversation[]> {
  const { data, error, response } = await api.GET('/api/v1/conversations')
  return requireData(data, error, response, '会话列表加载失败。').items
}

export async function createConversation(): Promise<Conversation> {
  const { data, error, response } = await api.POST('/api/v1/conversations', { body: {} })
  return requireData(data, error, response, '建立会话失败。')
}

export async function listMessages(conversationId: string, cursor?: string): Promise<MessagePage> {
  const { data, error, response } = await api.GET('/api/v1/conversations/{id}/messages', {
    params: { path: { id: conversationId }, query: { limit: 50, cursor: cursor ?? null } },
  })
  return requireData(data, error, response, '消息加载失败。')
}

export async function listDeskCaseSummaries(conversationId: string): Promise<DeskCaseSummary[]> {
  const { data, error, response } = await api.GET('/api/v1/conversations/{id}/case-summaries', {
    params: { path: { id: conversationId } },
  })
  return requireData(data, error, response, '案例摘要加载失败。')
}

export async function transitionMode(conversationId: string, body: components['schemas']['ModeTransition']): Promise<Conversation> {
  const { data, error, response } = await api.POST('/api/v1/conversations/{id}/mode-transitions', {
    params: { path: { id: conversationId } }, body,
  })
  return requireData(data, error, response, '协作策略更新失败。')
}

export async function requestAssistance(conversationId: string, reason: string): Promise<Task> {
  const { data, error, response } = await api.POST('/api/v1/conversations/{id}/assistance-requests', {
    params: { path: { id: conversationId } }, body: { reason },
  })
  return requireData(data, error, response, '人工协助请求失败。')
}

export async function listTasks(conversationId: string): Promise<Task[]> {
  const { data, error, response } = await api.GET('/api/v1/conversations/{id}/tasks', {
    params: { path: { id: conversationId } },
  })
  return requireData(data, error, response, '人工任务加载失败。')
}

export async function claimTask(taskId: string, expectedVersion: number): Promise<Task> {
  const { data, error, response } = await api.POST('/api/v1/tasks/{id}/claim', {
    params: { path: { id: taskId } }, body: { expected_version: expectedVersion },
  })
  return requireData(data, error, response, '任务接管失败，请刷新后重试。')
}

export async function listProposals(conversationId: string): Promise<Proposal[]> {
  const { data, error, response } = await api.GET('/api/v1/conversations/{id}/proposals', {
    params: { path: { id: conversationId } },
  })
  return requireData(data, error, response, '内部草稿加载失败。')
}

export async function decideProposal(proposalId: string, decision: 'APPROVED' | 'REJECTED', reason: string, decisionId: string): Promise<Proposal> {
  const { data, error, response } = await api.POST('/api/v1/proposals/{id}/decision', {
    params: { path: { id: proposalId } }, body: { decision_id: decisionId, decision, reason },
  })
  return requireData(data, error, response, '草稿审阅失败。')
}

export async function readUIDocument(conversationId: string): Promise<UIDocument | null> {
  const { data, error, response } = await api.GET('/api/v1/conversations/{id}/ui-document', {
    params: { path: { id: conversationId } },
  })
  return requireData(data, error, response, '交互卡加载失败。')
}

export async function refreshUIDocument(conversationId: string): Promise<UIDocument> {
  const { data, error, response } = await api.POST('/api/v1/conversations/{id}/ui-document/refresh', {
    params: { path: { id: conversationId } },
  })
  return requireData(data, error, response, '交互卡刷新失败，请继续使用文字消息。')
}

export async function invokeUIAction(conversationId: string, body: UIActionBody) {
  const { data, error, response } = await api.POST('/api/v1/conversations/{id}/ui-actions', {
    params: { path: { id: conversationId } }, body,
  })
  return requireData(data, error, response, '操作结果未确认，请用原请求重试或刷新任务。')
}

export async function sendMessage(conversationId: string, body: SendBody): Promise<MessageReceipt> {
  const { data, error, response } = await api.POST('/api/v1/conversations/{id}/messages', {
    params: { path: { id: conversationId } }, body,
  })
  return requireData(data, error, response, '发送结果尚未确认；可用原消息重试。')
}

export async function listDevices(): Promise<Device[]> {
  const { data, error, response } = await api.GET('/api/v1/devices')
  return requireData(data, error, response, '设备列表加载失败，请重试。')
}

export async function readDevice(id: string): Promise<Device> {
  const { data, error, response } = await api.GET('/api/v1/devices/{id}', { params: { path: { id } } })
  return requireData(data, error, response, '设备不存在或当前账号无权访问。')
}

export async function listDeviceCases(id: string): Promise<ServiceCase[]> {
  const { data, error, response } = await api.GET('/api/v1/devices/{id}/cases', { params: { path: { id } } })
  return requireData(data, error, response, '服务历史加载失败，请重试。')
}

export async function listCases(): Promise<ServiceCase[]> {
  const { data, error, response } = await api.GET('/api/v1/cases')
  return requireData(data, error, response, '案例列表加载失败。')
}

export async function readCase(id: string): Promise<ServiceCase> {
  const { data, error, response } = await api.GET('/api/v1/cases/{id}', { params: { path: { id } } })
  return requireData(data, error, response, '案例不存在或当前账号无权访问。')
}

export async function readResolutionContract(caseId: string): Promise<ResolutionContract> {
  const { data, error, response } = await api.GET('/api/v1/cases/{id}/resolution-contract', {
    params: { path: { id: caseId } },
  })
  return requireData(data, error, response, '解决条件加载失败。')
}

export async function listCaseVerifications(caseId: string): Promise<Verification[]> {
  const { data, error, response } = await api.GET('/api/v1/cases/{id}/verifications', {
    params: { path: { id: caseId } },
  })
  return requireData(data, error, response, '核验记录加载失败。')
}

export async function recordCaseVerification(caseId: string,
  body: components['schemas']['VerificationRequest']): Promise<Verification> {
  const { data, error, response } = await api.POST('/api/v1/cases/{id}/verifications', {
    params: { path: { id: caseId } }, body,
  })
  return requireData(data, error, response, '核验结果未确认，请用原编号重试。')
}

export async function listCaseEvidence(caseId: string, cursor?: string): Promise<EvidencePage> {
  const { data, error, response } = await api.GET('/api/v1/cases/{id}/evidence', {
    params: { path: { id: caseId }, query: { limit: 50, cursor: cursor ?? null } },
  })
  return requireData(data, error, response, '图片证据加载失败。')
}

export async function uploadCaseEvidence(caseId: string, file: File, clientEvidenceId: string,
  expectedCaseVersion: number, visibility: 'PUBLIC' | 'INTERNAL'): Promise<CaseImageEvidence> {
  const body = new FormData()
  body.set('client_evidence_id', clientEvidenceId)
  body.set('expected_case_version', String(expectedCaseVersion))
  body.set('visibility', visibility)
  body.set('file', file)
  const response = await fetch(`/api/v1/cases/${encodeURIComponent(caseId)}/evidence`, {
    method: 'POST', credentials: 'same-origin', body,
  })
  if (!response.ok) {
    const error: unknown = await response.json().catch(() => null)
    const detail = error && typeof error === 'object' && 'detail' in error ? (error as { detail: unknown }).detail : null
    throw new ApiFailure(response.status, typeof detail === 'string' ? detail : '图片上传失败。')
  }
  return response.json() as Promise<CaseImageEvidence>
}

export async function readCaseEvidenceImage(caseId: string, evidenceId: string): Promise<Blob> {
  const response = await fetch(`/api/v1/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/content`, {
    credentials: 'same-origin', cache: 'no-store',
  })
  if (!response.ok) throw new ApiFailure(response.status, '图片不可查看，可能尚未通过检查或当前账号无权访问。')
  return response.blob()
}

export async function listCaseActions(caseId: string): Promise<CaseAction[]> {
  const { data, error, response } = await api.GET('/api/v1/cases/{id}/actions', { params: { path: { id: caseId } } })
  return requireData(data, error, response, '售后动作加载失败。')
}

export async function requestMockAction(caseId: string, body: components['schemas']['MockActionRequest']): Promise<CaseAction> {
  const { data, error, response } = await api.POST('/api/v1/cases/{id}/action-requests', {
    params: { path: { id: caseId } }, body,
  })
  return requireData(data, error, response, '模拟动作请求结果未确认，请用原编号重试。')
}

export async function listActionApprovals(caseId: string): Promise<ActionApproval[]> {
  const { data, error, response } = await api.GET('/api/v1/cases/{id}/approvals', { params: { path: { id: caseId } } })
  return requireData(data, error, response, '审批记录加载失败。')
}

export async function decideActionApproval(id: string, body: components['schemas']['ActionApprovalDecision']): Promise<ActionApproval> {
  const { data, error, response } = await api.POST('/api/v1/approvals/{id}/decisions', {
    params: { path: { id } }, body,
  })
  return requireData(data, error, response, '审批结果未确认，请用原编号重试。')
}
