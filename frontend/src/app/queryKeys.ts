export const queryKeys = {
  actor: ['actor'] as const,
  health: ['health'] as const,
  devices: (tenantId: string, actorId: string) => ['devices', tenantId, actorId] as const,
  device: (tenantId: string, actorId: string, id: string) => ['device', tenantId, actorId, id] as const,
  deviceCases: (tenantId: string, actorId: string, id: string) => ['device-cases', tenantId, actorId, id] as const,
  caseFactReview: (tenantId: string, actorId: string, id: string) => ['case-fact-review', tenantId, actorId, id] as const,
  cases: (tenantId: string, actorId: string) => ['cases', tenantId, actorId] as const,
  case: (tenantId: string, actorId: string, id: string) => ['case', tenantId, actorId, id] as const,
  caseActions: (tenantId: string, actorId: string, id: string) => ['case-actions', tenantId, actorId, id] as const,
  caseEvidence: (tenantId: string, actorId: string, id: string) => ['case-evidence', tenantId, actorId, id] as const,
  resolutionContract: (tenantId: string, actorId: string, id: string) => ['resolution-contract', tenantId, actorId, id] as const,
  caseVerifications: (tenantId: string, actorId: string, id: string) => ['case-verifications', tenantId, actorId, id] as const,
  followUpConsents: (tenantId: string, actorId: string, id: string) => ['follow-up-consents', tenantId, actorId, id] as const,
  followUps: (tenantId: string, actorId: string, id: string) => ['follow-ups', tenantId, actorId, id] as const,
  caseActionApprovals: (tenantId: string, actorId: string, id: string) => ['case-action-approvals', tenantId, actorId, id] as const,
  conversations: (tenantId: string, actorId: string) => ['conversations', tenantId, actorId] as const,
  messages: (tenantId: string, actorId: string, conversationId: string) =>
    ['messages', tenantId, actorId, conversationId] as const,
  summaries: (tenantId: string, conversationId: string) =>
    ['case-summaries', tenantId, conversationId] as const,
  tasks: (tenantId: string, conversationId: string) => ['tasks', tenantId, conversationId] as const,
  proposals: (tenantId: string, conversationId: string) => ['proposals', tenantId, conversationId] as const,
  uiDocument: (tenantId: string, actorId: string, conversationId: string) =>
    ['ui-document', tenantId, actorId, conversationId] as const,
  knowledge: (tenantId: string, actorId: string) => ['knowledge', tenantId, actorId] as const,
  guard: (tenantId: string, actorId: string) => ['guard', tenantId, actorId] as const,
}
