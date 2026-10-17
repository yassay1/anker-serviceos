# Agent quality evaluation

`datasets/agent-quality-v1.jsonl` contains 78 de-identified cases: all 63 first-message tickets in the supplied hackathon workbook plus 15 additional safety, privacy, uncertainty, retrieval-boundary, and multi-turn scenarios. Workbook attachments and source order identifiers are not sent to the model. The ticket source labels are reference labels, not verified Anker policy.

`run_agent_quality_eval.py` creates a uniquely named local PostgreSQL database, applies the real migrations, initializes the LangGraph checkpoint schema and curated local knowledge/policy seeds, then starts the actual FastAPI API and Agent Worker as separate processes. It submits cases through the public message API and records, per turn, API acceptance, MessageJob state, AgentRun, model/token/timing details, tools, proposals, specialist runs, persisted events, and customer-visible reply. It does not start action workers or execute external service actions. Embedding calls are disabled; runtime retrieval uses the committed seed corpus.

Run from the repository root with an already configured, approved local Provider. The script reads the existing `.env` silently and does not copy it into the worktree:

```powershell
uv run --project backend --locked python backend/evaluations/run_agent_quality_eval.py --validate-only
uv run --project backend --locked python backend/evaluations/run_agent_quality_eval.py --env-file 'D:/proj/Anker SreviceOS/backend/.env'
```

By default, three multi-turn scenarios are each rerun twice in fresh conversations, for 84 conversation runs and 93 message turns. The evaluation worker is configured for one attempt per message to avoid repeated paid calls; retry behavior is not scored. Results contain case/turn IDs and sanitized final replies, but never model reasoning or API credentials. A timeout blocks further submissions and marks remaining cases not started; the chain ledger retains that fact. The isolated database is intentionally retained for post-run review and cleanup after any rerun.

For diagnosis, `--case-id CASE_ID` may be repeated to select specific cases. `--worker-log PATH` captures that run's Worker log in an explicitly chosen local file; logs omit prompts and exception text, and only record safe error classifications.
