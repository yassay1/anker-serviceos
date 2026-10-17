# Agent quality evaluation report · 2026-10-17

## Scope and method

- Dataset: `agent-quality-v1`, 78 cases: all 63 de-identified first-message tickets from the hackathon workbook plus 15 supplemental safety, privacy, boundary, uncertainty, and multi-turn cases.
- Execution: 84 fresh conversations, 93 customer-message turns. Each API submit returned HTTP 202. The public FastAPI route, persistent MessageJob, separate LangGraph Worker, local seeded knowledge/policy corpus, and real configured Provider were used. Provider telemetry identifies `openai-compatible` / `deepseek-flash` on `api.deepseek.com`.
- Each turn is recorded in the corresponding `case-results.jsonl`, including Job and AgentRun state, error code, timing, token usage, tool calls, proposals, specialist runs, persisted event types/visibility, and whether an actual public reply was visible. The result ledger stores sanitized final public replies and no model reasoning.
- Retries were limited to one attempt per message to control Provider usage. Embeddings, workbook attachments, and action workers were disabled; no external Anker action was executed. The workbook's hackathon labels are reference data, not verified Anker policy.
- The dataset manifest records 63 source tickets, 15 supplemental cases, the content hash, redaction counts, and a zero residual scan for emails, URLs, and long numeric identifiers.
- These measurements were collected from the evaluation worktree based on commit `e676bba`; the later interaction-contract changes on `main` are outside this recorded Provider run. The combined tree passed backend integration tests after merge, but the Provider dataset was not rerun on it.

The run design records complete tool and message trajectories in addition to task outcomes, following the trajectory-level evaluation approach in [τ-bench](https://openreview.net/pdf?id=roNSXZpUDN) and the trace-oriented evaluation model in [LangSmith](https://docs.langchain.com/langsmith/evaluation).

## Baseline and repaired run

| Measure | Baseline | After fix |
|---|---:|---:|
| Conversation runs | 84 | 84 |
| Message turns | 93 | 93 |
| Customer API submissions accepted | 93 / 93 | 93 / 93 |
| Case runs completed | 43 / 84 | 84 / 84 |
| Job / AgentRun completed | 44 / 93 | 93 / 93 |
| Job / AgentRun failed | 49 / 93 | 0 / 93 |
| Public replies persisted and visible | 39 / 93 | 81 / 93 |
| Internal Agent replies | 5 | 12 |
| Provider input / output tokens | 1,237,869 / 59,747 | 1,252,779 / 56,950 |
| Mean AgentRun duration | 17.8 s | 18.0 s |

The baseline failed on `agent_execution_failed` after the Agent had used the Provider. A one-case replay with safe exception classification found `NameError: safety` in `project_reply`: its normal-reply filtering branch referenced an undefined name. The Agent had generated a result, but the Worker failed before the reply could be published. The repaired full evaluation used the function's existing server-computed `assessment.triggered` value. A subsequent cleanup removed that condition because a triggered assessment already returns the server-owned safety reply earlier in the function. The cleanup passed the targeted and full PostgreSQL tests; the Provider dataset was not rerun after that behavior-preserving cleanup.

The 12 post-fix internal replies are persisted with `visibility=INTERNAL`; they are completed AgentRuns but are intentionally not counted as customer-visible replies. Their cases are `hk-ticket-009`, `hk-ticket-031`, `hk-ticket-038`, `hk-ticket-041`, `hk-ticket-045`, `hk-ticket-056`, `edge-knowledge-robot`, `edge-knowledge-pump`, `edge-ambiguous-model`, `edge-contradictory-facts`, and `edge-multiturn-emotion` turns 2 in repeat 0 and turn 1 in repeat 2. This distinction preserves the backend's publication policy instead of treating every completed run as an auto-reply.

## Agent and safety observations

- The repaired run completed all 63 ticket conversations and all 15 supplemental conversations. It recorded 168 `lookup_manual`, 47 `get_service_progress`, 31 `load_skill`, 18 `query_order_warranty`, 12 `delegate_diagnostic`, 8 `get_case_stage`, 6 `request_missing_evidence`, 4 `propose_action`, and 1 `resolve_policy` tool calls. It also recorded 21 internal action proposals and 12 specialist runs; no action execution worker was started.
- Both explicit hardware-hazard cases produced public replies containing the required stop-use and human-assistance guidance. Both privacy cases and both approval-boundary cases completed with public replies. These are targeted output checks, not a human/domain expert score of every answer.
- All three two-turn continuity scenarios completed in the original run and in both fresh-conversation repeats. Some turns correctly remained internal, as listed above.
- Semantic accuracy against verified product manuals and official service policy was not fully human-scored. The test knowledge set is a committed local seed and does not include workbook attachments. In particular, the 12 internal replies warrant review if customer-visible coverage is the target.

## Verification commands and results

- Dataset validation: `uv run --project backend --locked python backend/evaluations/run_agent_quality_eval.py --validate-only` — 78 cases validated; dataset SHA-256 `0c803ec727949314c5f5b4fb265bd297975177cd79b8988decb2bfbfcbfab0f8`.
- Full baseline: `uv run --project backend --locked python backend/evaluations/run_agent_quality_eval.py --env-file 'D:/proj/Anker SreviceOS/backend/.env'` — run `20261017T050210`, completed with 43 completed and 41 failed conversations.
- Targeted PostgreSQL tests after the fix — 5 passed.
- Full backend suite after the fix — `pytest backend/tests`: 352 passed, 0 failed, 2 existing PostgreSQL migration warnings.
- Full repaired evaluation: same command as baseline — run `20261017T055239`, completed with all 84 conversations and 93 turns successful.
- Follow-up undefined-name guardrail: Ruff F821/F823 added to the backend dev lock and CI; active backend scan passed, both rules rejected a temporary negative probe, targeted PostgreSQL tests passed (5), and the full backend suite passed (352, with the same 2 migration warnings).
- Merged `main` integration: Ruff, dataset `--validate-only` and OpenAPI drift checks passed. The first local full suite exposed that `SERVICEOS_ENV=test` loaded the developer `.env` and invoked the configured Provider during a specialist publication test (1 failed, 356 passed). After restricting local dotenv loading to development and adding an isolation test, the full PostgreSQL suite passed: 358 passed, 2 existing migration warnings.

The baseline ledger is `20261017T050210/case-results.jsonl`; the repaired ledger is `20261017T055239/case-results.jsonl`. Each is accompanied by `run-metadata.json`. An early pilot was stopped after its first two repeated Agent failures to avoid further retries; its two-case ledger is retained in `20261017T045806`. The short diagnostic replays and setup attempts are also retained; setup failures happened before any model request.
