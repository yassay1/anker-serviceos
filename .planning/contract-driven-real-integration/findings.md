# Findings: Contract-driven UI integration

## Repository facts
- Active application: single React + TypeScript + Vite frontend and FastAPI backend. `frontend/README.md` says actual integration follows real OpenAPI and generated Client; planned operations cannot be called.
- Current API source of truth: `backend/serviceos_api/api/business.py`, Pydantic schemas/application services, exported `contracts/openapi.json`, and generated `frontend/src/api/schema.d.ts`.
- Applicable workflow: `docs/templates/feature-contract.md` already requires role/tenant authorization, request/response/errors, idempotency/versioning, event visibility, reconnect/cursor behavior, and success/failure/concurrency/staleness verification.
- `/api/v1/conversations/{id}/assistance-requests` creates a human task. Task list and claim routes exist. No queue-duration/ETA API was identified; UI should display only factual task stage.
- Message contract carries author kind and PUBLIC/INTERNAL visibility; customer and staff message queries/event streams filter by authorization. Existing frontend separates recorded messages and local composer text, and displays progress from persistent `agent.progress` / `specialist.activity` events.
- No live-presence API was found in the inspected interface inventory. A dot may represent actual persisted task/run stage only if its exact meaning derives from server data; it must not imply online/availability.
- Staff proposals exist through list/decision routes; public publication remains behind server-side policy. The composer and timeline must not represent an unapproved proposal as sent.

## Official supplied internal materials and evidence boundary
- Product and system truth is in V1 docs: `docs/product-definition.md`, `docs/architecture.md`, `docs/domain-and-contracts.md`, `docs/development-plan.md`, plus `docs/baseline-integration.md` and `docs/contributing.md`.
- Runtime handbooks are in `backend/serviceos_api/knowledge/`; current files appear to be small seeded knowledge notes and corpus files, not a complete authoritative official Anker policy library.
- `data/reference/hackathon/README.md` explicitly says the official-provided, desensitized hackathon pack is scenario/reference input, not runtime knowledge, current formal Anker policy, or implemented API evidence. Its product Q&A and source `Published/Visible` labels do not establish current-policy validation.
- Prompt must require the executor to identify the source and authority level for every rule/answer; never silently upgrade hackathon samples into official policy.

## Mature project research (official product documentation)
- Intercom Inbox AI: agent-facing AI features require staff input/review; a human-in-loop handoff carries context and a draft, with distinct paths to approve, give missing facts, or take over. https://www.intercom.com/help/en/articles/6955446-ai-features-available-in-the-inbox
- Zendesk Agent Copilot: suggests replies/next steps and approved actions while keeping the agent in control. https://support.zendesk.com/hc/en-us/articles/7908817636378-About-agent-copilot
- Chatwoot's official user guide treats a private note as team-only and changes composer appearance to reduce public/private mistakes; its API material also exposes `private` in message payloads. https://app.chatwoot.com/hc/user-guide/articles/1677235281-lesson-3-a-mastering-core-features and https://www.chatwoot.com/hc/user-guide/articles/1677839703-how-to-create-an-api-channel
- Design transfer: keep the customer transcript to persisted public messages; render staff-only AI drafts/proposals in a clearly separate review surface; copy-to-composer is not send; make public/private mode unmistakable before commit; render handoff/agent progress from persisted lifecycle facts; preserve full context on handoff.

## Proposed contract-map dimensions
For each interaction: surface/role, user intent, trigger, source-of-truth state, route/operationId, request/response schemas, application-service ownership, authorization/tenant scope, visibility, idempotency/expected version, asynchronous event and cursor/reload rules, UI success/rejected/uncertain states, retry semantics, acceptance evidence, status (`implemented`/`gap`/`design-only`).
