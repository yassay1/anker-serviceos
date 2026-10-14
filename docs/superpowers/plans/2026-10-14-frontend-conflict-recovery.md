# Frontend conflict recovery implementation plan

> **For agentic workers:** Execute inline using the existing isolated checkout and the test-first steps below.

**Goal:** When the implemented collaboration API rejects a stale request with HTTP 409, show the rejection and refresh the authoritative state so obsolete actions disappear.

**Architecture:** Preserve the generated OpenAPI client, authentication and server authorization. Reuse the panel's existing invalidation path on both success and conflict; never replay a mutation automatically. Browser tests intercept only the HTTP boundary to reproduce unavailable SSE and defined server responses, and are not live backend acceptance.

**Tech Stack:** React, TanStack Query, generated OpenAPI types, Playwright/Chromium.

## Task 1: Reproduce the existing rejection path

Files: `frontend/tests/collaboration.spec.ts`, `frontend/playwright.config.ts`, `frontend/tsconfig.browser-tests.json`, `frontend/package.json`, `frontend/package-lock.json`, `.gitignore`.

- [x] Add exact dev dependency `@playwright/test@1.64.0` and script `test:browser: playwright test`.
- [x] Use a dedicated Vite test server on loopback port 5174. All API requests are intercepted in tests; production proxy and origins remain unchanged.
- [x] Add typed fixtures from `src/api/schema.d.ts`. Reproduce disconnected SSE plus OPEN task; claim returns 409 and the subsequent task read returns ASSIGNED. Assert that the error remains visible and the obsolete claim button disappears within 5 seconds, without a second mutation.
- [x] Add stale-mode and already-decided draft variants, and controls for a successful claim, policy refusal with an unchanged draft, and forbidden access with no fabricated assignment. Add the same-mode, version-only conflict variant identified during review. Exercise the conflict recovery at 390px using the keyboard.
- [x] Run `$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:browser`. Expect conflict recovery assertions to fail on the unchanged panel, while control cases pass.

## Task 2: Repair only the conflict refresh

File: `frontend/src/features/collaboration/CollaborationPanel.tsx`.

- [x] Import `ApiFailure` from the existing client.
- [x] Extract the existing four invalidations into local `refreshState()` and retain the success call.
- [x] In the existing catch block, preserve `setError(readableError(failure))`, then add:

```ts
if (failure instanceof ApiFailure && failure.status === 409) {
  await refreshState()
}
```

- [x] Synchronize the mode selection when `conversation.version` changes as well as when its mode changes. Verify the new version-only test fails before this repair.
- [x] Run the same tests and verify the failed cases now pass. No automatic claim/decision/mode retry; 403 remains a refusal.

## Task 3: Verify and hand off

Files: `.github/workflows/ci.yml`, `frontend/README.md`, `docs/frontend-integration-validation.md`, `docs/phase3-validation.md`.

- [x] Add the browser test check after the existing frontend build in CI, installing Chromium with `npm exec -- playwright install --with-deps chromium`.
- [x] Run `npm run check:api`, `npm run typecheck`, `npm run build`, `npm run test:browser`; check actual backend OpenAPI using Python 3.12 after locked dependency installation.
- [x] Record source baseline, affected files, screenshots, failure-before/fix-after evidence, exact commands and limits. Keep live PostgreSQL/SSE/provider acceptance pending unless actually executed.
- [x] Review the diff and prepare the validated handoff on `codex/frontend-phase3-integration`.
- [ ] Commit, push to the private repository and create a draft PR with the validation evidence; do not merge. This final delivery step is tracked by the PR itself.

## Verified plan adjustment

Windows CRLF conversion changed the raw OpenAPI byte hash while Git retained the original LF bytes. Add `.gitattributes` with `/contracts/openapi.json text eol=lf`; normalize only the working-copy line endings and verify the proposal check succeeds without any staged contract content change. Both checks were executed.
