# 交互与真实业务契约对齐验收记录（feature 018）

日期：2026-10-17

本记录只覆盖本次客户/客服交互增量，不改变其他阶段的验收状态，也不代表生产或真实 Anker 系统验收。

## 已完成范围

- 客户可查询本人发起的协助任务安全状态；状态来自 `CustomerAssistanceRead`，只显示 OPEN/ASSIGNED/CLOSED，不推断 ETA、在线或正在查看。
- 客服可读取同租户 OPEN/MINE 任务队列，复用既有带版本的 task claim。
- AI 回复建议复制为持久客服草稿；进入回复框、编辑、审批和发送为不同状态。批准不发布；发送经 Conversation Service 重新授权并以持久 `MessageReceipt` 为准。
- 新增 `assistance.status_changed` 安全公开事件投影。客户时间线不接收草稿、proposal 或 INTERNAL 消息。
- 真实 FastAPI/OpenAPI 与生成前端 Client 同源；新增 `StaffReplyDraft` 持久表和 migration 0021。

## 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run --project backend --locked pytest -q` | 167 passed, 204 skipped。被跳过项包含需 PostgreSQL/显式集成环境的用例；不能据此称为全套 PostgreSQL 验收。 |
| `uv run --project backend --locked ruff check backend/serviceos_api/application/contracts.py backend/serviceos_api/application/services.py backend/serviceos_api/api/business.py backend/serviceos_api/persistence/models.py backend/tests/test_business_api.py backend/tests/test_worker_runtime.py` | All checks passed. |
| `uv run --project backend --locked python -m serviceos_api.export_openapi --check` | OpenAPI matches the actual application. |
| `npm run check:api` | API types match OpenAPI. |
| `npm run typecheck` | TypeScript application and browser-test typechecks passed. |
| `npm run build` | Build succeeded. Vite reports the existing 500 kB chunk-size advisory (main JS 513.84 kB). |
| `npm run test:browser -- --reporter=line` | 99 passed. |
| `npm run test:live -- --reporter=line` | 6 passed against an isolated temporary local PostgreSQL database and alternate local ports. The wrapper migrated and seeded only that temporary database, then verified no active sessions and dropped it. No existing `serviceos_dev` database or occupied user process was used. |

此前对 migration round-trip 的定向检查通过，包含索引名核对；隔离 live run 也覆盖真实本地 API/DB。测试未调用 LLM、外部服务或真实 Anker 售后 API。

## 未实现与限制

- 没有 presence、ETA、排队时长/SLA、取消/重派/关闭任务、团队队列等契约；界面不展示这些内容。
- 客户协助状态仅反映真实 TaskRead。请求受理不是客服接手。
- 草稿审批人可与编辑人相同；当前项目没有 maker-checker 业务约束。
- 真实 Anker 售后系统、生产身份提供方、生产数据库/浏览器及真实模型质量未验收；Mock 与本地服务仍不能宣称真实外部执行。
- 自动浏览器/live 验收通过不等于用户手动目视签收或部署准入。

详细操作/事件/schema/授权/租户/visibility/幂等/版本/失败恢复映射见 [`specs/018-interaction-contract-alignment/contracts/feature-contract.md`](../specs/018-interaction-contract-alignment/contracts/feature-contract.md)。
