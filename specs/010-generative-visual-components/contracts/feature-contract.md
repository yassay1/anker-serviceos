# Generative visual components contract

## Scope

Add two inert, versioned UI components to the existing UIDocument path:

- `KnowledgeMetricChart` renders a fixed server-owned bar chart from one packaged knowledge item marked Published/Visible in the supplied workbook. The Agent may request the component and identify the allowlisted knowledge item; it never supplies values.
- `CaseProcessFlow` renders staff-only Case, Task, mock Action, and Verification states from current authorized business records. The Agent may request it and identify a linked Case; it never supplies node states, labels, or edges.

The UI document remains a projection. Neither component changes business state or exposes a new action.

## Initial knowledge metric

The first chart uses the supplied workbook row for eufy Wearable Breast Pump S1 Pro (T8D04): heating duration 5/10/15 minutes and approximately 10/20/30% additional battery use. Its note must say the values are source estimates, not device telemetry. The server serves it only when a verified linked Device Passport has model T8D04, and only from the packaged knowledge entry with its current content hash. No customer/order rows are imported. Workbook status does not independently verify current manufacturer policy or content usage rights; customer-facing use requires approval.

## Schema additions

`UIComponent` gains optional `chart` and `flow` payloads. Exactly one payload is allowed, and only on its matching catalog type.

`chart` is a bounded `BAR` payload with metric id, x/y labels, unit, 2–8 distinct labeled finite points, source label/version, and an explanatory note. For the initial chart, values and metadata are fixed by the server source adapter.

`flow` has at most 8 nodes and 8 edges. Node IDs and statuses are allowlisted; each node has a title, neutral detail, and authorized source reference/version. Edges must reference existing distinct nodes, contain no duplicate pair, and form an acyclic graph. Flow data is staff-only.

## Authorization and freshness

- UI proposals stay internal until projected through ConversationService.
- A customer chart requires a current CUSTOMER AgentRun proposal, a linked verified T8D04 Device Passport, AI_LEAD + AI_AUTO, and the allowlisted metric source. It contains no case/order/identity PII.
- A process flow requires a STAFF actor, INTERNAL audience, a current linked Case, and current Case/Task sources. It is read-only; all displayed states come from server records.
- Existing tenant/resource authorization, publication policy, revision, expiry, and text fallback remain authoritative. Frontend validation is defense-in-depth only.
- Unknown source, invalid values, unsupported catalog, stale version, or non-staff flow request must be rejected or fall back safely.

## Acceptance

Cover successful chart and flow projection/rendering; model mismatch; unpublished/invisible/unknown metric; malformed numeric payload; unauthorized flow/audience; unlinked resource; invalid graph edges/cycle; old catalog and unsupported data fallback; PUBLIC/INTERNAL separation; and no actions on either visual component.
