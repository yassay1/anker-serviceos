# Task plan: Implement Visible Specialist Orchestration

## Goal
Implement the user-approved visible Diagnostic Agent orchestration in `specs/011-visible-specialist-orchestration`, in dependency order A → B → C → D. Preserve Service Agent as the user-facing coordinator; keep Jev deferred. This work is authorized for application implementation, but excludes unrelated features, cloud/deployment changes, and any new agent framework.

## Phases
- [x] Phase 0: Reconcile approved decisions, requirements, plan, task coverage, and run the Spec Kit read-only consistency gate.
- [x] Phase A: Delegate Diagnostic Agent from Service Agent and persist reliable, bounded structured results.
- [x] Phase B: Publish specialist identity/progress/result through existing Outbox/SSE and render in the existing UI.
- [x] Phase C: Persist diagnostic questions/answers and resume the same task across AgentRuns, timeout, and lease retries. Hard process-kill/provider checkpoint validation remains unverified.
- [x] Phase D core: Integrate approved experience references, manual/Skill boundaries, current Case/Device/evidence revalidation, deterministic safety/human-review exits, and publication policies. A staff provenance review component remains an explicit follow-up, not shipped.
- [x] Final for this implementation slice: Full backend/PostgreSQL suite, OpenAPI drift, frontend type/API checks, specialist browser flows, docs consistency, and diff review completed. Real-provider latency/quality and hard process-kill recovery are unverified.

## Constraints and approved decisions
- User confirmed the recommended approach and explicitly deferred Jev.
- Retain current LangChain/LangGraph stack; use manager-controlled Tool Subagent, not Handoff or a new framework.
- Service Agent remains the sole user-facing coordinator and publication authority.
- Specialist receives a narrow typed task, read-only/allowlisted capabilities, bounded budget, and returns structured result; no raw reasoning is exposed.
- `AI_REVIEW_REQUIRED` / `CO_SERVICE`: specialist progress/result is staff-only by default; backend publication authorization remains authoritative.
- User-pending diagnostic task default expiry: 7 days, without notification commitment.
- Distinguish checkpoint state from business DiagnosticTask/verified facts. No model guess becomes verified device fact.
- Follow root AGENTS.md, docs/contributing.md for cross-boundary contract work, module READMEs, and constitution. Add focused tests for success, failure, authorization, idempotency, and recovery.
- No unrelated work or deployment/cloud configuration changes.

## Phase 0 analysis summary
- Added US4 to cover SOP/collaboration integration, which had task coverage but no user story in the old spec.
- Explicitly included authorized task status read for refresh/reconnect state reconciliation.
- Coverage mapping: FR-001–003: T010–016; FR-004: T010/T012/T014; FR-005: T018–024; FR-006: T008/T009/T018/T020/T021/T038; FR-007: T029–033; FR-008: T007–011/T015/T026–031; FR-009: T005–009; FR-010: T034–038; FR-011: T014/T015/T030/T031; FR-012: T011/T018/T026/T027/T034/T039. SC-001: T010; SC-002: T011/T015; SC-003: T018/T021/T023; SC-004: T018/T019/T022/T030/T033; SC-005: T034/T037; SC-006: T039.
- Constitution alignment: evidence/fact separation, SOP deterministic authority, bounded tools, ConversationService publication, durable business state separate from checkpoint, and focused PostgreSQL tests are represented.
- No critical or high consistency blockers remain. Exact migration/revision and OpenAPI/front-end generation changes will be resolved against current code when the relevant stage begins.

## Errors / decisions
| Issue | Attempts | Resolution |
|---|---:|---|
| Prior plan said implementation was forbidden after user approval | 1 | Updated active plan while preserving prior docs-only work in progress history |
| Original spec had no story covering planned SOP integration | 1 | Added independently testable US4 and linked it to Stage D tasks |
| `.specify/feature.json` was pinned to feature 005 | 1 | Used `SPECIFY_FEATURE_DIRECTORY` for the 011 prerequisite gate, then restored existing selector |

## Current status
Stages A–D code and documentation were completed in this slice. Open follow-ups are T035/T037 staff provenance browser/UI scope and T039 real-provider/hard-kill acceptance; these are listed explicitly in the feature task plan and are not represented as shipped.
