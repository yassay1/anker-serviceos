# 可见 Specialist 委派：已实现契约与边界

> 状态（2026-10-16）：阶段 A–D 的功能代码已实现。本文按实际 Pydantic schema、SQLAlchemy models、ConversationService 和前端 Renderer 记录；不等同真实 Provider 生产验收。没有专属诊断 GET/POST API。Jev 按用户要求搁置。

真实 API 以 FastAPI + `application/contracts.py` 为准。导出：`uv run --project backend --locked python -m serviceos_api.export_openapi`；漂移检查加 `--check`。前端在 `frontend/` 执行 `npm run generate:api` / `npm run check:api`。SSE 复用 `EventRead.data`，没有新增路由。诊断 answer 改动已体现在现有 `UIActionRequest`/`UIActionResult` OpenAPI 与生成 Client。

## 架构和生命周期

```mermaid
sequenceDiagram
  participant U as Customer/Staff
  participant API as Conversation API
  participant DB as Business PostgreSQL
  participant W as MessageWorker
  participant S as Service Agent
  participant D as Diagnostic Agent
  participant CP as LangGraph Checkpoint
  participant CS as ConversationService/Outbox
  participant UI as SSE + UI Renderer
  U->>API: POST customer message
  API->>DB: Message + MessageJob + Outbox
  API-->>U: fast receipt
  W->>S: authorized AgentContext + current message
  S->>DB: create/reuse DiagnosticTask + SpecialistRun under parent lease
  CS->>DB: fixed specialist.activity at real transition
  DB-->>UI: sequenced PUBLIC/INTERNAL event
  S->>D: typed minimal DiagnosticTaskInput + allowlisted tools
  D->>CP: specialist thread checkpoint
  D-->>S: validated DiagnosticResult (HYPOTHESIS)
  S->>DB: revalidate sources; persist result + WAITING/COMPLETED state
  S->>CS: parent agent response; latest policy decides publication
  opt WAITING_CUSTOMER
    UI->>API: existing UIAction submit-diagnostic-answer
    API->>DB: validate actor/task/UI/question; atomically save Message + Answer + Job + Outbox
    API-->>UI: accepted receipt
    W->>S: new AgentRun for answer Message
    S->>D: same task + persisted answer; rebuild context in new thread
  end
```

`DiagnosticTask` is durable business state. `SpecialistRun` is a bounded attempt identity and points to a checkpoint thread. A lease retry may reuse that SpecialistRun/thread; a later customer answer creates a new parent AgentRun and rebuilds specialist context from the persisted task and answer. Checkpoint is not authoritative for customer answer, Case, verified facts, or message publication.

Status values: task `QUEUED/RUNNING/WAITING_CUSTOMER/WAITING_STAFF/COMPLETED/FAILED/CANCELLED/EXPIRED`; specialist run `QUEUED/RUNNING/COMPLETED/FAILED/INTERRUPTED`. `WAITING_CUSTOMER` expiry is 7 days and is currently enforced lazily during authorized UI projection and answer submission; there is no scheduler. `WAITING_STAFF` records safety stop/human review. `COMPLETED` is diagnostic completion only, never Case resolution.

## Typed DiagnosticTaskInput v1

Server constructs this DTO; model cannot provide tenant/customer authorization or arbitrary resource references. Current fields are `schema_version`, `task_id`, `conversation_id`, bounded `goal`, `case_refs[]` (id/version/problem), `device_refs[]` (id/revision/identity status/verified facts), `evidence_refs[]` (ref/kind/summary), up to two reviewed `experience_examples[]`, and up to eight public-history snippets. Current implementation's Diagnostic Agent uses only fixed read-only manual lookup and eligible Skill tools. Candidate experience remains reference material and is revalidated against its approved source before result persistence.

## Typed DiagnosticResult v1

```json
{
  "schema_version": 1,
  "task_id": "uuid",
  "assessment": "可能是供电连接问题",
  "certainty": "HYPOTHESIS",
  "confidence_band": "LOW",
  "evidence_refs": [{"ref_id": "authorized-evidence-id", "supports": "用户报告的现象"}],
  "unknowns": ["尚未确认线材规格"],
  "next_step": {"kind": "ASK_CUSTOMER", "summary": "确认使用的线材", "safety": null,
                 "question": {"prompt": "线材是什么接口？", "options": ["USB-C", "其他"]}},
  "staff_summary": "当前假设和证据缺口"
}
```

`next_step.kind`: `EXPLAIN | ASK_CUSTOMER | REQUEST_EVIDENCE | SAFETY_STOP | HUMAN_REVIEW | NO_ACTION`; ASK_CUSTOMER requires a question. Question prompt/options are bounded and reject obvious PII/markup/URL patterns. `certainty` is fixed to `HYPOTHESIS`; result references must belong to server-authorized task refs or validated manual sources. Model output never promotes DeviceFact, Evidence verification or Case state.

## Durable answer and UI Action

Migration `0015_diagnostic_tasks.py` adds DiagnosticTask/SpecialistRun; `0016_diagnostic_answers.py` adds versioned question fields and DiagnosticAnswer. `DiagnosticAnswer` binds tenant/task/question revision, unique client action, customer and source Message. The customer does not call a new endpoint: server projects an authorized `DIAGNOSTIC_TASK_VIEW` question with action `submit-diagnostic-answer` / intent `SUBMIT_DIAGNOSTIC_ANSWER` / schema `serviceos://ui-inputs/diagnostic-answer/v1` into the existing controlled UI document.

Current endpoint is `POST /api/v1/conversations/{id}/ui-actions`. The request is the existing `UIActionRequest`: `{client_action_id, ui_id, revision, action_id, input, expected_conversation_version}`. The inner answer input is exactly `{task_version, question_revision, answer}`. Server verifies current customer owner, active conversation, AI_LEAD + AI_AUTO, exact UI revision/source binding, task version/status, question revision/options and expiry. In one transaction it writes a customer Message, DiagnosticAnswer, MessageJob, UIActionInvocation and Outbox events. Same idempotency action replays the original result; stale/different payload conflicts. MessageWorker asynchronously handles the answer; HTTP does not wait for model execution.

No standalone `GET /diagnostic-tasks/{id}` or `POST /diagnostic-tasks/{id}/answers` is registered. Refresh obtains question from authorized current UI projection; status/activity uses existing event history/SSE and Message projection. This deliberate choice avoids a duplicate authorization surface.

## Specialist activity event

One event type `specialist.activity` has a strict Pydantic payload: `task_id`, `specialist_run_id`, fixed `agent_type=DIAGNOSTIC`, `display_name=诊断专家`, allowlisted `stage` (`STARTED/LOOKUP/RESULT_READY/WAITING_CUSTOMER/WAITING_STAFF/FAILED`), bounded `summary`, and `certainty` (`HYPOTHESIS/NONE`). Event IDs are deterministic per specialist attempt/stage. Parent AgentRun lease and task/run ownership are validated before Outbox write; dispatch rereads current collaboration mode/reply policy. `AI_LEAD+AI_AUTO` may see PUBLIC activity; other policies default INTERNAL. Existing SSE history/sequence and actor visibility filters apply. Event is not a chat Message and does not contain prompts, reasoning, token stream, tool names/arguments/results, private notes or secrets.

Result event summaries are safety-checked with conservative fallback. `SAFETY_STOP`/`HUMAN_REVIEW` use fixed safe response. The original 011 slice did not persist specialist results as chat authors; the separately approved [feature 017 contract](../../017-specialist-author-messages/contracts/feature-contract.md) adds one SPECIALIST-authored projected result per eligible SpecialistRun through ConversationService. `AI_LEAD + AI_AUTO` may receive PUBLIC output after the current publication guard; `CO_SERVICE`, `AI_REVIEW_REQUIRED` and `HUMAN_LEAD/HUMAN_ONLY` retain INTERNAL staff-visible output. The Service Agent remains coordinator and should not repeat a persisted specialist result.

## Ownership, concurrency, failure and limits

- Dependency direction: API/renderer → application authorization and projection → domain persistence; worker → AgentRuntime; agents → typed application query/tool interfaces; only ConversationService publishes messages/UI/events.
- Tenant-scoped foreign keys and task version protect associations; unique answer per task/question revision and tenant/client action enforce answer idempotency; one active SpecialistRun per task; parent lease fences specialist writes and events.
- Every completion revalidates Case, Device Passport, evidence and reviewed experience state. Current-result publication rechecks conversation status and policy. No model hypothesis is a verified fact.
- Duplicate UI action returns the saved receipt; conflicting action payload, stale UI/task/question, unauthorized actor, expired question, unsupported choice and changed policy are rejected without queueing a second answer.
- Worker lease retry reuses the SpecialistRun checkpoint thread; later answer gets a distinct thread and rebuilds from DB task/answer. Provider checkpoint state loss and hard process termination were not exercised end to end. Failure never asserts diagnosis completed; safety/human paths wait for staff.
- Public activity has fixed status summaries only. Raw reasoning and tool outputs are not event/UI contract. Specialist result in the existing internal event is not a full provenance review surface; a staff evidence/source review card remains unimplemented.
- SOP remains in deterministic application services; RAG platform/vector index is absent. Current knowledge is local read-only handbook, fixed Skill and approved experience candidates. Jev is deferred and has no adapter/client.

## Known unverified items

Real-provider structured output, policy/quality behavior, P50/P95 latency/tokens, forced process-kill recovery, a background expiry scheduler and staff provenance review UI are not claimed as complete. Check `.planning/visible-specialist-orchestration/progress.md` for exact commands and evidence.
