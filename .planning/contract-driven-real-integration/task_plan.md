# Plan: Contract-driven UI integration

## Goal
After user approval, reconcile the approved mobile-first conversation/staff design with actual ServiceOS APIs, events, permissions, application services, and official project materials; maintain a traceable contract map and implement only supported behaviors, creating reviewed contracts for any real gaps.

## Current status
Research and plan drafted. Awaiting user approval before implementation or changes to active product/design docs.

## Phases
- [x] Research: inspect repository baseline, current frontend/backend/API contract sources, and official supplied materials boundaries.
- [x] Research: compare mature support workflows and message/draft visibility practices using official product documentation.
- [ ] After approval, inventory each visible interaction and classify it as existing contract, missing contract, or design-only/inappropriate to imply.
- [ ] Maintain a contract map and agree any missing cross-module contracts before implementation.
- [ ] Implement customer and staff flows through existing application services and generated API client; add a backend contract only where evidence proves a gap.
- [ ] Run scoped backend, OpenAPI/client, frontend, and real-API/browser verification; update acceptance record and plan status based only on evidence.

## Scope guardrails
- Do not treat mockup labels, sample dialogue, static indicators, or documentation proposals as implemented business facts.
- No fabricated ETA, live-agent presence, task completion, AI message, or operation receipt.
- PUBLIC/INTERNAL authorization remains server-owned; private notes, proposal content, and raw model reasoning never reach customer view.
- The V1 rules and actual FastAPI/OpenAPI remain authoritative; official hackathon data is scenario reference, not current Anker policy or proof of integrations.
- No deployment, production identity integration, real Anker API call, or external service changes.

## Acceptance outline
Each planned interaction maps to: customer/staff intent → UI state → actual route/operation → schema → application service → persisted event/read model → authorization/visibility → success/rejection/retry/recovery → verification evidence.

## Pending user decision
Approve the scoped contract reconciliation and implementation plan, or narrow/reorder its items.
