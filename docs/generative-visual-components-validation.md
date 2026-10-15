# Generative visual components: implementation and validation

Date: 2026-10-16

Status: implemented and locally validated. The user approved the public contract and customer-facing use of the supplied source; PostgreSQL projection acceptance remains pending.

## Scope and status

This increment extends the existing Agent → UIDocument → Catalog/Policy Validator → Renderer path. It adds two inert visual components and no new route, business write, database migration, or npm dependency.

| Capability | Status | Boundary |
|---|---|---|
| Versioned UIDocument, trusted catalog, audience/visibility checks, authorized resource references, revision/expiry fallback | Already implemented | Existing publication path and ConversationService remain authoritative |
| `KnowledgeMetricChart` | Implemented in this increment | Agent selects an allowlisted source; server emits the fixed three-point estimate only for a linked, verified T8D04 device; no telemetry or customer/order data |
| `CaseProcessFlow` | Implemented in this increment | Staff-only projection of current linked Case, Task, Mock Action, and Verification states; read-only |
| SVG renderer and accessibility text | Implemented in this increment | Fixed bar and flow rendering; no generated HTML, script, URL, or action payload |
| PostgreSQL projection acceptance | Added, not verified here | Three integration tests skipped because `SERVICEOS_TEST_DATABASE_URL` is not configured |
| Real model/provider decision quality | Not evaluated | Browser and runtime tests use controlled fixtures; no live model/provider credentials used |

## Contracts and trust boundaries

### `KnowledgeMetricChart`

- The only current metric is `heating-extra-battery` from the supplied S1 Pro Q&A entry, which is marked Published/Visible in that workbook: 5/10/15 minutes maps to approximately 10/20/30% extra battery use.
- `knowledge_source_id` is allowlisted. The Agent cannot send points, axes, units, or source version. The server reads the packaged knowledge entry, checks publication/visibility/model markers and exact points, and fingerprints the source text.
- Projection requires a public Agent response eligible under the existing AI lead/automatic reply policy and a linked Device Passport whose identity is verified and model is T8D04. The server does not currently verify that the same AgentRun called `lookup_manual`; it independently checks the packaged source and its fixed values. The displayed note says the values are published estimates, not device telemetry.
- The frontend repeats exact metric/value/source-shape checks and falls back to text on mismatch.

### `CaseProcessFlow`

- The Agent may request a staff flow and select a case ID; the Case must be among the cases already linked to the authorized conversation context.
- The backend queries current Case, Task, Mock Action, and Verification records and projects allowlisted node IDs, statuses, source references, and edges. The Agent cannot submit node/edge/status content.
- Both backend and frontend validate component type, STAFF audience, CASE/TASK resource references and versions, node/status allowlists, edge references, duplicate edges, and acyclicity. The component has no actions and is never accepted for a customer document.
- Rendered details are staff-only (`INTERNAL`); existing ConversationService publication, tenant/resource authorization, current revision, expiry, and fallback rules still apply.

Neither component turns a model suggestion into a verified device fact or claims an action succeeded. Completion labels come only from the durable Case/Action/Verification state projections. External actions continue through their existing application services and authorization checks.

## Rollout recommendation

1. Keep the fixed T8D04 estimate as the first production-shaped chart example; verify the source remains published and visible when its upstream knowledge process changes.
2. Use the Case flow for staff review of current durable state. Validate PUBLIC/INTERNAL separation and resource freshness before expanding to other audiences.
3. Add future charts only through curated metric adapters with source, applicability, units, ranges, and evidence checks. Add a general graph library or chart dependency only when actual branching/interaction requirements exceed the current static SVG components.
4. Before broader rollout, rerun the projection tests against the disposable PostgreSQL test database and measure fallback/validation-error rates. Evaluate real-provider component selection separately from rendering correctness.

## Validation run in isolated worktree

- Backend focused pure/API tests: `python -B -m pytest backend/tests/test_agent_result.py backend/tests/test_ui_catalog.py backend/tests/test_ui_visualizations.py backend/tests/test_api_baseline.py backend/tests/test_observability.py -q` — 46 passed, using the existing backend environment.
- PostgreSQL projection selection: `python -B -m pytest backend/tests/test_worker_runtime.py -k "customer_projection_builds_metric or customer_metric_is_suppressed or staff_projection_builds_case_flow" -q` — 3 skipped because `SERVICEOS_TEST_DATABASE_URL` is not configured. No database integration result is claimed.
- OpenAPI export and `--check`, proposed V1 sync and `--check`, frontend Client generation, `npm run typecheck`, `npm run build` — passed. The isolated frontend used `npm ci --ignore-scripts --prefer-offline` against the existing lockfile; no dependency was added.
- `npm run test:browser -- tests/delivery-readiness.spec.ts -g 'metric|process flow'` — 4 passed.
- Customer-facing knowledge content and its usage rights/current accuracy still need approval. `Published/Visible` are fields in a user-supplied workbook, not an independently verified live manufacturer policy.
