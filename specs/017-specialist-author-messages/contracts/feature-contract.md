# 功能契约：诊断专家作者消息

## Contract status

Confirmed for implementation on 2026-10-17. This contract adds a persisted specialist-authored Message to the existing diagnostic orchestration; the specialist runtime itself has no public messaging capability.

## Message identity

- `author_kind` is `SPECIALIST` for the diagnostic result message.
- `messages.specialist_run_id` is required exactly when `author_kind=SPECIALIST`, tenant-scoped to `specialist_runs`; it is unique per tenant to cap each invocation at one result message.
- Specialist messages have no customer/staff actor identity. The server fixes the display name to `诊断专家`; clients cannot supply authorship or source run fields.
- The read contract includes the author kind. It does not expose the source run UUID to customers. Existing `SendMessage` schema does not change to accept specialist fields.

## Visibility and eligibility

| Current conversation state/policy | Result message |
|---|---|
| `ACTIVE + AI_LEAD + AI_AUTO`, valid content guard | `PUBLIC` |
| Other active, authorized collaboration policies | `INTERNAL` |
| Inactive conversation, waiting for customer answer, invalid lease/source, failed result | No result message |
| `SAFETY_STOP` / `HUMAN_REVIEW` | No specialist-authored free-form message; existing fixed safety/human-review response and activity event remain authoritative |

Dispatch must never promote an INTERNAL message/event to PUBLIC. Customer history and SSE continue to use existing server-side visibility filtering. Human review of INTERNAL output does not automatically approve a customer reply; an authorized human may send a separate ordinary STAFF message.

## Content and lifecycle

- The message is a bounded server projection of the validated `DiagnosticResult.assessment` plus an independently safety-checked next-step summary when appropriate. It is labeled `初步假设（待核验）`.
- `staff_summary`, raw model reasoning, tool names/arguments/results, secrets, private notes, and raw evidence/source text are excluded.
- `ASK_CUSTOMER` continues through the existing diagnostic question UI projection and creates no duplicate chat question.
- Only `ConversationService` persists the Message. `AgentToolService.complete_diagnostic` invokes the publication path after validating the current task, run, lease and evidence. The task result, Message, and `message.created` Outbox event commit in one transaction.
- `(tenant_id, specialist_run_id)` provides replay idempotency. Same source/result returns the existing row; a conflicting payload fails closed.
- The Service Agent remains coordinator. Its tool result indicates that a specialist message was recorded, and its follow-up should provide only distinct coordination/next-action text.

## Read and real-time behavior

- Existing paged message history and `message.created` event refresh deliver the author kind. No specialist send/read endpoint or new SSE event type is introduced.
- The frontend maps `SPECIALIST` to fixed `诊断专家` and displays an `AI 假设（待核验）` label. Specialist messages do not enable Agent quick replies or rich-action affordances.
- Existing tenant/resource authorization and PUBLIC/INTERNAL filtering apply unchanged.

## Required verification

- PostgreSQL checks: valid and invalid author/source combinations, cross-tenant FK rejection, one message per SpecialistRun, policy visibility, lease rejection, idempotency and transaction atomicity.
- API checks: author kind is returned, customer cannot read INTERNAL, and SendMessage rejects/ignores no untrusted attribution fields (strict extra-field behavior is verified).
- OpenAPI export and generated Client are synchronized.
- Frontend browser check covers public and internal author rendering and confirms specialist messages do not offer quick replies.
