# Findings: Visible Specialist Orchestration implementation

## Approved design baseline
- The user approved the recommended architecture and asked to proceed with implementation using the planning skill.
- Jev is explicitly deferred because the repository has no current integration.
- Build in stages A–D, subject to the current source implementation and spec analysis.
- Manager-controlled Tool Subagent is the selected control model; Service Agent owns final response and publication.
- Existing dependency lock (as of prior research): LangChain 1.4.5, LangGraph 1.2.15, langgraph-checkpoint-postgres 3.1.3. Reconfirm when coding against APIs.
- Default specialist visibility for `AI_REVIEW_REQUIRED` / `CO_SERVICE` is staff-only; Service Agent/backend remains publication authority.
- Proposed user-pending diagnostic expiry is 7 days. Verify this matches the actual task/retention infrastructure before finalizing implementation.

## Repository implementation evidence (2026-10-16; reconfirm before changes)
- Service Agent runtime: `backend/serviceos_api/agents/runtime.py`; current runtime has four registered tools and fixed model/tool/recursion/output budgets.
- Worker lifecycle: `backend/serviceos_api/worker/runtime.py`; per-message AgentRun and job lease/heartbeat/retry; outbox progress is currently coarse/fixed.
- Context builder and app services: `backend/serviceos_api/application/agent_services.py`, `application/services.py`, `application/contracts.py`.
- Persistence and API: `backend/serviceos_api/persistence/models.py`, `api/business.py`.
- Frontend live events and safe UI rendering: `frontend/src/features/conversation/useConversationEvents.ts`, `frontend/src/features/ui-document/UIDocumentRenderer.tsx`.
- Existing `ServiceTask` serves human collaboration, not specialist execution. Agent checkpoint and business state are separate.
- Local handbook retrieval is read-only paragraph ranking; Skill registry is fixed; only `diagnose-no-charge` is callable; `emotion-assessment` is prepared. Jev integration is absent.
- Previous turn updated baseline docs and `specs/011-visible-specialist-orchestration/{spec,research,plan,tasks,contracts}` as design-only. Reconcile artifacts with this authorization before implementation.

## Open implementation questions
- How the current frontend generated API/client is produced and whether API answer submission can reuse a typed existing route without violating semantics.
- The smallest durable task/run schema compatible with current migration conventions and worker leases.
- Whether per-task specialist checkpointing is already supported cleanly by current AgentRuntime construction.
- Whether an existing outbox event allowlist and authorization matrix can accept `specialist.*` without broadening visibility.

## Phase A implementation checks (2026-10-16)
- Installed locked LangChain 1.4.5 `create_agent` supports `response_format`, and existing middleware exposes per-run `run_limit` for model/tool calls. This confirms current dependency can support typed specialist output and bounded calls without a new framework.
- `SERVICEOS_TEST_DATABASE_URL` is not configured in this shell. PostgreSQL acceptance will require finding a safe local test database path; the test fixture creates/drops only a uniquely named disposable database and refuses non-PostgreSQL URLs.
- Current parent Worker holds job/conversation/run fencing; each typed tool creates a short SQLAlchemy session, validates the active lease, commits its side effect and returns bounded data. Specialist tool facade must reuse that parent lease authority and must not create independent public messages.
