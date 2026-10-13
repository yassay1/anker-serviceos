# Backend based frontend implementation plan

**Goal:** Bring the approved frontend presentation into the existing typed, authenticated application using only implemented backend capabilities.

**Architecture:** Reuse the current query/client/service boundary. Plain CSS and Lucide extend the established blue/light design; no second state store or mock business layer. Devices are a read-only projection of existing APIs.

## 1. Tests first

- Add `frontend/tests/workspace.spec.ts` with typed transport fixtures. Assert local conversation search, mobile view switching, per-conversation draft preservation, review-reason validation, real device fields/history and permission refusal.
- Run `npm run test:browser -- --grep 'adaptation'`; confirm missing behavior fails before implementation.

## 2. Existing surfaces

- Update `frontend/src/App.tsx`, `app/ServicePage.tsx`, `features/conversation/*` and `features/collaboration/CollaborationPanel.tsx`.
- Keep authentication/cache clearing and typed mutations. Add per-conversation draft map, search/filter, mobile panels, readable status labels and operation feedback. Set `disabled={busy || reason.trim().length < 3}` on review actions and trim the reason submitted.
- Rewrite `styles/base.css` and `styles/workspace.css` in the existing styling system. Add reusable status/error presentation under `shared/`.

## 3. Read-only devices

- Add typed `listDevices`, `readDevice`, `listDeviceCases` wrappers in `api/client.ts`, calling the existing GET paths.
- Add identity-scoped query keys and `features/devices/DevicesWorkspace.tsx`; route `/devices` and `/devices/:id` through the current auth boundary.
- Render authoritative identity state, model, masked serial, verified facts with source, and case history. Provide loading, empty, error/retry and forbidden states; never fall back to another device after an inaccessible explicit ID.

## 4. Verification and delivery

- Keep existing seven HTTP rejection/success tests, update copy assertions to the actual translated labels without weakening behavioral assertions.
- Add a separate `frontend/playwright.live.config.ts` and `tests-live/service-flow.spec.ts` for existing local auth and actual API/DB interaction. CI prepares only its ephemeral PostgreSQL database, API and Vite on allowed loopback ports.
- Run check:api/typecheck/build and browser tests. Batch desktop/mobile screenshots and axe checks, fix findings together, confirm once. Review code and UI independently, record evidence and limits.
- Push the existing private branch and update draft PR #3 around the final frontend change. Await actual CI results; do not merge or deploy.
