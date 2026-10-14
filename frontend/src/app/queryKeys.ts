export const queryKeys = {
  actor: ['actor'] as const,
  health: ['health'] as const,
  devices: (tenantId: string, actorId: string) => ['devices', tenantId, actorId] as const,
  device: (tenantId: string, actorId: string, id: string) => ['device', tenantId, actorId, id] as const,
  deviceCases: (tenantId: string, actorId: string, id: string) => ['device-cases', tenantId, actorId, id] as const,
  conversations: (tenantId: string, actorId: string) => ['conversations', tenantId, actorId] as const,
  messages: (tenantId: string, actorId: string, conversationId: string) =>
    ['messages', tenantId, actorId, conversationId] as const,
  summaries: (tenantId: string, conversationId: string) =>
    ['case-summaries', tenantId, conversationId] as const,
  tasks: (tenantId: string, conversationId: string) => ['tasks', tenantId, conversationId] as const,
  proposals: (tenantId: string, conversationId: string) => ['proposals', tenantId, conversationId] as const,
  uiDocument: (tenantId: string, actorId: string, conversationId: string) =>
    ['ui-document', tenantId, actorId, conversationId] as const,
}
