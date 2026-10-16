# Tasks: Visible Specialist Orchestration

**Input**: `specs/011-visible-specialist-orchestration/spec.md`, `plan.md`, `research.md`, `contracts/feature-contract.md`
**Prerequisites**: spec.md, plan.md
**Tests**: Required by the repository constitution and spec. Follow test-first for each vertical slice; use isolated PostgreSQL for persistence, authorization, idempotency, and recovery.

## Phase 1: Setup and shared contracts

**Purpose**: Freeze approved assumptions, verify module boundaries, and define the typed contracts before coding.

- [x] T001 Update `specs/011-visible-specialist-orchestration/spec.md`, `plan.md`, `research.md`, and `contracts/feature-contract.md` to record approval, defer Jev, resolve default visibility/expiry, and distinguish design from implemented status.
- [x] T003 [P] Add focused schema tests for valid, invalid, oversized, untrusted-reference and enum payloads in `backend/tests/test_diagnostic_contracts.py`.
- [x] T002 Add versioned DiagnosticTask/DiagnosticResult contracts in `backend/serviceos_api/application/diagnostic_contracts.py`; event and answer types are intentionally added with Stages B/C.
- [x] T004 Record current OpenAPI generation and frontend API generation commands and ownership in `specs/011-visible-specialist-orchestration/contracts/feature-contract.md`.

## Phase 2: Foundational persistence and authorization

**Purpose**: Add durable business task/run identity and transaction-safe boundaries required by all user stories.

- [x] T007 [P] Add model/migration invariant tests for tenant ownership, legal states, one active run per task, uniqueness/idempotency and nullable Case association in `backend/tests/test_diagnostic_tasks.py`.
- [x] T009 [P] Add application-service tests for parent-run ownership, duplicate/conflicting delegation, stale references, invalid evidence, current-resource version, and idempotent result persistence in `backend/tests/test_diagnostic_tasks.py`.
- [x] T005 Add DiagnosticTask and SpecialistRun SQLAlchemy models, constraints, indexes and status/version fields in `backend/serviceos_api/persistence/models.py`.
- [x] T006 Add reversible migration for diagnostic task/run persistence in `backend/migrations/versions/0015_diagnostic_tasks.py`; preserve existing case/conversation relationships and migration chain.
- [x] T008 Define DiagnosticTask application service operations, authorization checks, current-resource/version validation, idempotency and lease fencing in `backend/serviceos_api/application/agent_services.py`.

## Phase 3: User Story 1 — Service Agent delegates a diagnostic (Priority: P1, Stage A)

**Goal**: Keep Service Agent in control while a restricted Diagnostic Agent returns a schema-validated, durable result.

**Independent Test**: Existing easy requests do not delegate; an eligible request creates one task/run and returns a structured hypothesis citing only authorized evidence; invalid output, tool escalation, worker retries and lease loss cannot create trusted facts or duplicate effects.

### Tests first

- [x] T010 [P] [US1] Add AgentRuntime tests for optional manager delegation, bounded call limits, specialist tool allowlist and invalid result rejection in `backend/tests/test_agent_runtime.py` and `backend/tests/test_diagnostic_contracts.py`.
- [x] T011 [P] [US1] Verify PostgreSQL Worker lease/failure/result-reuse paths in `backend/tests/test_worker_runtime.py` and child task idempotency/fencing in `backend/tests/test_diagnostic_tasks.py`.

### Implementation

- [x] T012 Add a restricted Diagnostic Agent runtime with structured output and read-only manual/fixed-skill tools in `backend/serviceos_api/agents/diagnostic.py`; approved-experience composition remains Stage D.
- [x] T013 Add server-built minimal task context and authorized evidence/source/version validation in `backend/serviceos_api/application/agent_services.py` and `backend/serviceos_api/application/diagnostic_contracts.py`.
- [x] T014 Add the typed diagnostic delegation tool to `backend/serviceos_api/agents/runtime.py`; enforce call/model/output budgets and return only a bounded result to the manager.
- [x] T015 Reuse the existing asynchronous `MessageWorker` lease and `AgentRuntime.invoke` path for task creation, SpecialistRun execution/result persistence and same-lease/idempotent recovery; no Worker code change was needed in `backend/serviceos_api/worker/runtime.py`.
- [x] T016 Persist diagnostic result only as a bounded hypothesis; reject stale/unapproved references and do not mutate Case/Passport/Conversation or publish directly in `backend/serviceos_api/application/agent_services.py`.
- [x] T017 Run focused US1 tests and record success/failure/permission/retry/lease-recovery evidence in `.planning/visible-specialist-orchestration/progress.md`.

## Phase 4: User Story 2 — User/staff can see safe specialist activity (Priority: P2, Stage B)

**Goal**: Project real specialist identity, allowlisted work stages, and authorized result summary through existing Outbox/SSE and controlled UI.

**Independent Test**: AI_AUTO receives real persisted started/progress/result events; restricted policies receive staff-only activity; history/reconnect is consistent; event content never includes raw reasoning/tool payloads.

### Tests first

- [x] T018 [P] [US2] Add ConversationService/Outbox/SSE tests for specialist event schemas, deterministic idempotency, current-policy recheck, PUBLIC/INTERNAL filtering and replay in `backend/tests/test_worker_runtime.py`.
- [x] T019 [P] [US2] Add frontend tests for specialist event decoding, identity/status projection, reconnect and internal-event non-display in `frontend/tests/delivery-readiness.spec.ts`.

### Implementation

- [x] T020 Add typed allowlisted `specialist.activity` event creation, idempotency and policy revalidation in `backend/serviceos_api/application/services.py` and `backend/serviceos_api/application/diagnostic_contracts.py`.
- [x] T021 Reuse the existing generic `EventRead`/SSE envelope and PUBLIC/INTERNAL filters; no route or API schema change was needed in `backend/serviceos_api/api/business.py`.
- [x] T022 Add specialist event decoding/state reconciliation in `frontend/src/features/conversation/useConversationEvents.ts` and `frontend/src/features/conversation/ConversationWorkspace.tsx`.
- [x] T023 Add a controlled specialist activity/result component in `frontend/src/features/conversation/ConversationContext.tsx`; render safe event fields outside the chat message list.
- [x] T024 No OpenAPI type regeneration was needed because `EventRead.data` is already a generic object; existing generated API contract remains unchanged.
- [x] T025 Run focused backend and frontend US2 tests plus API contract drift/type checks; record evidence in `.planning/visible-specialist-orchestration/progress.md`.

## Phase 5: User Story 3 — Customer answers and resumes the same diagnostic (Priority: P3, Stage C)

**Goal**: Persist typed questions/answers and resume the same DiagnosticTask safely in a later Worker execution.

**Independent Test**: One valid answer advances the same task; replay is idempotent; conflicting, stale, expired, unauthorized and concurrent answers are rejected; worker/checkpoint interruption remains recoverable from business state.

### Tests first

- [x] T026 [P] [US3] Add application/API-boundary tests for answer acceptance, actor ownership, stale/replay conflict, shape, deadline and current reply policy in `backend/tests/test_diagnostic_api.py`.
- [x] T027 [P] [US3] Add PostgreSQL retry/recovery tests for one answer per task/question revision, task version fencing, same SpecialistRun lease takeover, same-task reconstruction and cached completion in `backend/tests/test_diagnostic_api.py`; process-kill/provider checkpoint validation remains unverified.
- [x] T028 [P] [US3] Add controlled UI action submission coverage and rely on existing shared Action conflict/recovery paths in `frontend/tests/delivery-readiness.spec.ts`.

### Implementation

- [x] T029 Add `DiagnosticAnswer`/question-version persistence and reversible migration `0016_diagnostic_answers.py`; existing `MessageJob` is the asynchronous resume queue.
- [x] T030 Add owner/current-question/task-version/idempotency/deadline validation through the existing authorized current UI projection and `POST /conversations/{id}/ui-actions`; a separate task API was unnecessary because UI refresh and event history already provide authorized state reconciliation.
- [x] T031 Add deterministic answer-to-task resume in `AgentContextBuilder`/`AgentRuntime`, fenced by parent run lease; Worker remains unchanged and uses existing MessageJob. New answer invocations rebuild the specialist context from persisted task/answer; a lease retry reuses the same specialist checkpoint thread.
- [x] T032 Add catalogued `SUBMIT_DIAGNOSTIC_ANSWER`, versioned question source, and controlled answer form in `ui_catalog.py` and `UIDocumentRenderer.tsx`.
- [x] T033 Export OpenAPI, regenerate frontend client, run focused US3 tests and record retry/recovery evidence in `.planning/visible-specialist-orchestration/progress.md`.

## Phase 6: User Story 4 — Diagnostic recommendations align with SOP and collaboration (Priority: P4, Stage D)

**Goal**: Integrate verified context and diagnostic candidates with SOP and human review without allowing the model to own workflow or verified facts.

**Independent Test**: SOP state transitions remain deterministic; a specialist hypothesis cannot resolve a case or become a verified fact; current reply policy and safety rules govern staff/customer visibility and human takeover.

### Tests first

- [x] T034 [P] [US4] Add integration tests for safety stop/human review publication guards and retain existing verified-vs-reported, unverified model/manual applicability, case version and reply-policy tests in `backend/tests/test_diagnostic_tasks.py` and `backend/tests/test_worker_runtime.py`.
- [ ] T035 [P] [US4] Remaining: add staff-review, case-fact provenance and human-takeover browser/live scenarios. Customer specialist identity/history and controlled-answer browser scenarios exist in `frontend/tests/delivery-readiness.spec.ts`; no separate staff provenance UI is implemented, so these additional scenarios wait for that approved product surface.

### Implementation

- [x] T036 Integrate reviewed experience references and typed questions with current evidence, fixed Skill/manual boundaries, and server-enforced SAFETY_STOP/HUMAN_REVIEW exits; retain SOP/Case status in existing domain services without duplicating state.
- [ ] T037 Remaining product/UI slice: expose authorized staff-only DiagnosticTask result and candidate provenance through existing Conversation/UI projection boundaries; require existing verification services before promotion. Current internal activity is visible, but there is no provenance review component, and no model candidate can currently be promoted directly.
- [x] T038 Revalidate case/device/evidence/reviewed-experience sources before result persistence, current reply policy at Outbox dispatch, and fixed safety/human-review response guards at publication in `backend/serviceos_api/application/agent_services.py` and `application/services.py`.
- [ ] T039 Partially complete: focused US4 source tests, OpenAPI check, frontend type/API checks and customer specialist browser scenarios pass. Remaining: run approved real-provider call/token/latency baseline and hard process-kill recovery when provider/acceptance environment is available; record these as NOT RUN, not simulated.

## Phase 7: Polish and cross-cutting verification

**Purpose**: Validate governance constraints, contract consistency, and completion status without misrepresenting unavailable evidence.

- [x] T040 [P] Update `docs/product-definition.md`, `docs/architecture.md`, `docs/domain-and-contracts.md`, `docs/service-sop.md`, `docs/development-plan.md`, and `docs/references.md` to distinguish implemented capability from remaining design and to preserve prior acceptance history.
- [x] T041 Run `git diff --check`, full backend/PostgreSQL tests, OpenAPI drift check, and frontend checks required by changed surfaces; write exact commands and outcomes to `.planning/visible-specialist-orchestration/progress.md`.
- [x] T042 Review authorization, privacy, data lineage, idempotency, migration rollback, event replay and recovery paths; update `specs/011-visible-specialist-orchestration/` and `docs/development-plan.md` with actual completed/unverified scope. Remaining staff provenance UI, real-provider and process-kill items are explicitly uncompleted above.

## Dependencies & Execution Order

- Phase 1 precedes all implementation; Phase 2 precedes US1-4.
- US1 / Stage A precedes US2 / Stage B because visible events require durable specialist identity/result.
- US2 precedes US3 / Stage C because the question and resume UI/event contract relies on task identity and public/staff event projection.
- US4 / Stage D depends on US1 and can begin after its result schema is stable, but final integration acceptance depends on US2/US3 persistence and policy gates.
- Phase 7 follows all selected stories. All stories are implemented sequentially by priority in this workstream; [P] only marks independent test authoring opportunities, not a request to parallelize.

## Implementation Strategy

1. Complete Phase 0 consistency analysis and resolve any blocking gaps before code.
2. Complete Phase 1/2 shared contract and persistence foundations.
3. Deliver A as a vertical slice; verify before B.
4. Deliver B, then C; preserve business-task recovery independent of checkpoint availability.
5. Integrate D after the result/event/question contracts stabilize.
6. Stop at phase boundaries to report evidence and risks, then continue the user-approved scope unless a true product decision blocks correctness.

## Notes

- Do not create a generic Agent Registry or replace the current runtime framework.
- Keep Jev deferred; no adapter or dependency is added.
- No model reasoning, raw tool output, or private context may appear in public event/UI contracts.
- A tool subagent is not a handoff: Service Agent remains responsible for final response and all public release.
