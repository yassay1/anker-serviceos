# Reference UI surfaces

Mode: Operate. Audience: customer and staff using the existing authenticated service workflow. Scope: frontend presentation only.

## Direction contract

THESIS: Match the user's five supplied compositions, keeping real service records and existing actions at the center.

OWN-WORLD: Warm ivory canvas, white panels, navy Chinese system typography, saturated blue actions, pale peach conversation bubbles. Room photography is decorative; device identity remains real text from the API. Plain CSS extends the existing React interface; no downloaded typeface is needed for the pinned direction.

STORY: A customer describes a new issue, opens a new conversation with the problem retained as an unsent draft, confirms before sending, then checks actual evidence and service progress. Staff scans loaded cases, opens a conversation, reviews authorized information and performs existing collaboration actions.

FIRST VIEWPORT: Home has a broad room hero and problem form left; diagnosis has a compact banner and conversation left with help right; service detail has a wide identity strip above three working columns; staff overview has navy rail, greeting, loaded-record counts and case table; console has rail, conversation list, chat, assistance panel.

FORM: User-pinned references, code-led implementation; no random concept seed supersedes the approved layouts. The reference-to-route mapping below defines this presentation pass.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance. Documentation of implemented styles does not itself constitute a visual pass.

Constraints: No API/schema/backend/database/config changes. Unsupported screenshot metrics, warranty, logistics, articles and model probabilities are omitted or explicitly unavailable. Existing evidence, fact review, recovery, approval and follow-up controls remain reachable. PRODUCT.md retains business authority.

## Approved references and implemented surfaces

| Pinned reference | Current route | Implemented composition |
|---|---|---|
| `docs/design-references/support/customer-home.png` | `/` for customer identity | Warm room hero, problem entry, six problem categories, real service and device records |
| `docs/design-references/support/ai-diagnosis.png` | `/support` | Compact warm banner, service path, collapsible conversation selector, conversation and assistance panels |
| `docs/design-references/support/service-detail.png` | `/cases/:id` | Broad case identity strip, record overview, progress/actions, problem/evidence, collaboration/verification/follow-up |
| `docs/design-references/desk/workbench.png` | `/desk?view=overview` (also `/` for staff identity) | Navy staff rail, greeting, scoped record counts, case table, collaboration shortcuts |
| `docs/design-references/desk/case-detail.png` | `/desk` | Staff rail, conversation queue, messages and composer, authorized case/assistance controls |

The durable visual system is in `DESIGN.md` and `.impeccable/design.json`. Source extraction follows `frontend/src/styles/base.css`, `workspace.css`, then `surfaces.css`; later surface rules override the older workspace defaults. Key current values are a 90px desktop header, 1800px main container, 176px staff rail, blue primary operations, peach own-message bubbles and three case-detail columns. These are implementation facts, not a visual acceptance verdict.

## Assets and business-data boundaries

`frontend/public/images/service-room.png` is generated decorative room photography reused in page heroes. Its prompt and provenance are recorded in `docs/assets/service-room.md`; it is separate from actual device records and must not be described as a product photo, customer's room, or diagnostic evidence. Device and case symbols are generic Lucide icons. The five supplied reference PNGs remain reference material, rather than shipping page backgrounds.

Home opens a new conversation through the existing creation API and transfers the required problem text as an unsent draft. Sending still uses the existing composer and idempotent message path. The page title “智能诊断” does not establish that a production model has run. Current model, production identity and external-service limitations remain as stated in PRODUCT.md and the actual API.

Staff counts are calculated from currently loaded authorized cases, conversations and devices. The case-list interface returns at most 50 records; the table explicitly states this range. Local search and filters operate on loaded records. Empty, loading and failure states remain visible; reference-image counts, probabilities, warranty promises, logistics progress and article libraries are not substituted. Mock service actions retain their explicit simulation labeling and approval/result separation.

## Review evidence

Round 1 evidence is in `.impeccable/review/reference-round1/`. The completed second-round evidence is in `.impeccable/review/reference-round2/`; all ten captures were usable in the final review. Each round contains the following ten PNGs:

| Surface | Desktop file | Mobile file |
|---|---|---|
| Customer home | `home-desktop.png` | `home-mobile.png` |
| Customer conversation | `support-desktop.png` | `support-mobile.png` |
| Service detail | `case-desktop.png` | `case-mobile.png` |
| Staff overview | `overview-desktop.png` | `overview-mobile.png` |
| Staff console | `desk-desktop.png` | `desk-mobile.png` |

Configured capture viewports are desktop 1448 × 1086 and mobile 390 × 844. Desktop captures cover the viewport; mobile captures cover the full page and can be taller than their viewport. A PNG can exclude the 10px scrollbar, so its raster width can differ from the configured viewport width. These images support presentation review; controlled browser fixtures are not proof of production data, a real model response, real logistics, or a successful external service action. Existing adaptation screenshots belong to an earlier design and do not establish acceptance of this reference pass.

Final review on 2026-10-15: **ship**. The reviewer inspected the complete second-round set and found no further material visual fixes. Earlier capture, case-column, console-identity, contrast and documentation findings were resolved.

Final controlled validation passed 81 Playwright tests (70 existing and 11 new), including 12 desktop/mobile Axe scans with zero violations and viewport-containment checks. `check:api`, typecheck and production build passed after the final source changes. These checks establish the tested frontend behavior and controlled accessibility results; they do not broaden the business capabilities described in PRODUCT.md.

Real-API browser checks read authorized records on customer home, customer conversation, service detail, staff overview and staff console. This run wrote no new business records. Writes and retries were validated in controlled tests; the live write closed loop was not rerun. No real AI provider is configured, and these checks do not claim a production-model diagnosis or successful external service execution.

The shipping-raster provenance scan checked one raster with zero missing embedded prompts; its accompanying prompt record is `docs/assets/service-room.md`. No detector was run for this pass. An older `.impeccable/review/detect.json` is not evidence for the current UI.
