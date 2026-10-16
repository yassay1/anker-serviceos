# 诊断专家作者消息验收记录

日期：2026-10-17。功能契约：[feature 017](../specs/017-specialist-author-messages/contracts/feature-contract.md)。

## 已实现范围

- `Message.author_kind=SPECIALIST`，并以 tenant-scoped `specialist_run_id` 记录来源；数据库约束要求来源完整且每个专家运行最多一条消息。
- 诊断完成后由 ConversationService 从已验证结果投影专家消息；结果、消息和 `message.created` Outbox 同事务提交，重试复用已有消息。
- `AI_LEAD + AI_AUTO` 使用现有公开内容检查后写 PUBLIC；其他有效策略写 INTERNAL。用户追问继续显示在诊断问题卡；安全停止/人工复核不发布专家自由文本。
- 消息读契约返回 SPECIALIST 作者类型及服务端固定显示名“诊断专家”；普通消息写接口不接受作者和来源字段。
- 前端历史消息显示“诊断专家 / AI 假设（待核验）”；专家消息没有 Agent 的 RichReply/快捷回复处理。Service Agent 收到已发布状态提示，避免复述专家结论。

## 变更文件

- 后端：`backend/serviceos_api/persistence/models.py`、`backend/migrations/versions/0019_specialist_author_messages.py`、`backend/serviceos_api/application/contracts.py`、`backend/serviceos_api/application/services.py`、`backend/serviceos_api/application/agent_services.py`、`backend/serviceos_api/agents/runtime.py`。
- 后端测试：`backend/tests/test_diagnostic_tasks.py`、`backend/tests/test_diagnostic_api.py`。
- 契约生成：`contracts/openapi.json`、`frontend/src/api/schema.d.ts`。
- 前端：`frontend/src/features/conversation/MessageThread.tsx`、`frontend/src/styles/workspace.css`、`frontend/src/styles/staff.css`、`frontend/tests/workspace.spec.ts`、`frontend/tests/workspace-fixture.ts`。
- 文档：`specs/017-specialist-author-messages/`、`specs/011-visible-specialist-orchestration/contracts/feature-contract.md`、`docs/domain-and-contracts.md`、`docs/development-plan.md`、`README.md`。

## 实际执行命令与结果

本地测试使用 `serviceos-postgres-local` 的回环 PostgreSQL；测试夹具为每次运行创建唯一 `serviceos_test_*` 数据库，并在结束时删除。未使用 `.env` 凭据或生产数据库。

| 命令 | 结果 |
|---|---|
| `uv run --project backend --locked pytest backend/tests/test_diagnostic_tasks.py backend/tests/test_diagnostic_api.py -q --require-postgres` | 26 passed |
| `uv run --project backend --locked pytest backend/tests/test_agent_runtime.py::test_customer_answer_resumes_persisted_task_before_manager_reply backend/tests/test_database.py::test_real_postgres_migration_round_trip backend/tests/test_diagnostic_tasks.py -q --require-postgres` | 19 passed；仅有既有 pgvector introspection / computed default 提示 |
| `uv run --project backend --locked pytest backend/tests --require-postgres -q` | 345 passed in 79.06s；仅有既有 pgvector introspection / computed default 提示 |
| `uv run --project backend --locked python -m serviceos_api.export_openapi` | 已导出 `contracts/openapi.json` |
| `uv run --project backend --locked python -m serviceos_api.export_openapi --check` | OpenAPI 与实际 FastAPI 应用一致 |
| `npm run generate:api` | 已更新 `frontend/src/api/schema.d.ts` |
| `npm run check:api` | API 类型与 OpenAPI 一致 |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过；Vite 提示主 bundle 约 507 kB，超过默认 500 kB 提示阈值 |
| `npm run test:browser -- --grep "specialist result has its own author"` | 1 passed |
| `uv run --project backend --locked ruff check backend/serviceos_api/agents/runtime.py backend/serviceos_api/application/agent_services.py backend/serviceos_api/application/contracts.py backend/serviceos_api/application/services.py backend/serviceos_api/persistence/models.py backend/migrations/versions/0019_specialist_author_messages.py backend/tests/test_diagnostic_api.py backend/tests/test_diagnostic_tasks.py` | All checks passed |
| `git diff --check` | 通过；Git 仅提示若干文件将 LF 转为 CRLF |

## 未实现 / 风险

- 未调用真实模型 Provider；结构化结果的真实质量、延迟及下游回复是否总能避免语义重复，仍需真实 Provider 与人工体验验收。
- 专家来源 UUID 不返回客户 API；staff provenance review 仍使用现有消息和活动摘要，没有建设单独的来源审查面板。
- 安全停止/人工复核仅发布既有固定回复和活动状态，不创建专家自由文本消息。
- 真实 Anker API、生产身份系统和生产部署不在本切片范围。
