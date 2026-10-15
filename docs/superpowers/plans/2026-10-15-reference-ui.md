# Reference UI Implementation Plan

> Execute inline in the running frontend; the user has approved the five reference layouts and asked to continue without stage approvals.

**Goal:** Rebuild the five reference surfaces while preserving the existing API client and every business control.

**Architecture:** Shared identity-aware header and staff navigation; read-only home/dashboard aggregation using current Client methods. Existing conversation/case/device features retain mutation, recovery, permissions and polling logic.

**Tech Stack:** React, TypeScript, React Router, TanStack Query, plain CSS, Lucide.

- [x] Baseline: run 70 existing controlled browser tests with Chrome; add failing home draft-handoff and dashboard filtering tests.
- [x] Shared shell: modify App.tsx and ServicePage.tsx; keep original auth boundaries and actor-scoped remounts.
- [x] Customer home: create features/overview/CustomerHome.tsx. Query existing cases/devices/conversations; pass an unsent draft via router state to the existing composer. Never automatically send or create a case.
- [x] Staff overview: create features/overview/DeskOverview.tsx at /desk?view=overview. Show counts from loaded records with explicit limits, filtering and original case links. Keep /desk as the existing console.
- [x] Conversation: preserve all request and recovery handlers, improve layout, add a collapsible customer service selector and neutral step guide. Keep authoritative UI cards.
- [x] Case detail: restructure existing evidence/actions/verification/follow-up panels into the reference hierarchy, add a server-state summary rather than guessed process milestones.
- [x] Visual system: shared tokens, room photo asset with provenance, consistent cards/typography/states; responsive layouts for desktop/tablet/mobile.
- [x] Verify: check:api, typecheck, build, all controlled browser tests; compare five desktop and mobile screenshots, fix as a batch, capture a second confirmation round; finish review and design documentation.
- [x] Delivery: update module/API mappings and visual difference report; preserve existing database/runtime configuration.

Validation: 81/81 controlled browser tests pass; check:api, typecheck, build pass. Two visual rounds completed; fresh full round-2 review: ship. DESIGN.md and schema-version-2 sidecar synchronized. Detailed evidence: docs/reference-ui-validation.md.
