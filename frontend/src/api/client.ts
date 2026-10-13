import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export type Actor = components['schemas']['ActorRead']
export type Conversation = components['schemas']['ConversationRead']
export type Message = components['schemas']['MessageRead']
export type MessagePage = components['schemas']['MessagePage']
export type MessageReceipt = components['schemas']['MessageReceipt']
export type SendBody = components['schemas']['SendMessage']

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

export async function readActor(): Promise<Actor> {
  const { data, error, response } = await api.GET('/api/v1/auth/me')
  return requireData(data, error, response, '登录状态暂时无法确认。')
}

export async function loginLocal(username: string, password: string): Promise<Actor> {
  const { data, error, response } = await api.POST('/api/v1/local-auth/login', { body: { username, password } })
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

export async function sendMessage(conversationId: string, body: SendBody): Promise<MessageReceipt> {
  const { data, error, response } = await api.POST('/api/v1/conversations/{id}/messages', {
    params: { path: { id: conversationId } }, body,
  })
  return requireData(data, error, response, '发送结果尚未确认；可用原消息重试。')
}
