# 阶段 3 实际验收记录：真人与 Agent 共同服务

日期：2026-10-13

## 已实现范围

- `/desk` 展示 Case 摘要、来源与核验状态，并按客服租户权限过滤。
- 人工任务、领取竞争、协作模式和发言策略切换、版本冲突、草稿审批；`HUMAN_LEAD`/`HUMAN_ONLY` 下旧 Agent 不能公开发言，但授权内部工作仍可记录。
- `ConversationEvent` 持久化，PUBLIC/INTERNAL 过滤，事件历史和 SSE `Last-Event-ID`/`after` 补取；断线不会重启 Agent。
- 版本化 `UIDocument`、受信 Catalog、服务端 Schema/Policy Validator；`/support` 与 `/desk` 使用受控 Renderer，未知或不支持内容降级到文本/固定表单。
- 低风险 `request-human-assistance` action intent 经应用服务重新鉴权、版本检查、幂等键和状态检查。

阶段 2 的真实 Provider 仍为“待验”。本阶段没有把 Mock 或离线替身结果描述成真实 Anker 操作，也没有创建云资源。

## 关键验收证据

| 检查 | 命令/结果 |
|---|---|
| PostgreSQL 业务回归 | `$env:SERVICEOS_TEST_DATABASE_URL='postgresql+psycopg://serviceos_local:serviceos_local_only@127.0.0.1:55432/serviceos_dev'; uv run --project backend --locked pytest backend/tests -q --require-postgres` → `65 passed` |
| 迁移升级 | `uv run --project backend --locked alembic -c backend/alembic.ini upgrade head` → 成功 |
| 迁移漂移 | `uv run --project backend --locked alembic -c backend/alembic.ini check` → `No new upgrade operations detected` |
| OpenAPI 同源 | `uv run --project backend --locked python -m serviceos_api.export_openapi --check` → matches actual application |
| 前端 Client | `cd frontend; npm run generate:api; npm run check:api` → 通过 |
| 前端类型与构建 | `npm run typecheck; npm run build` → 通过，Vite 72 modules |

回归覆盖：两名客服同版本领取仅一人成功；切换 `HUMAN_LEAD` 后公开 Agent 消息被拒、授权内部工作可继续；审批拒绝不执行动作；客户读取不到 INTERNAL 消息/事件/UI；事件断线补取按序列继续；旧 UI revision、越权数据源和未知组件被拒绝或降级；action intent 重复提交只产生一次结果。

## `/support` 与 `/desk` 复核

API 路由、应用服务和前端构建均已通过；本地 API 可由 `/support`、`/desk` 访问真实接口。浏览器自动化实际打开 `/support` 后，页面持续停留在“正在确认登录状态…”，而同一 API 的 `/api/v1/health` 可响应、未登录 `/auth/me` 返回 401。该本地浏览器登录加载问题未被记为成功，因此 UI 端到端成功/拒绝/恢复分支仍需在可用的本地浏览器会话中复验。

## 未实现或待真实环境验收

- 真实模型 Provider 的多轮服务、结构化工具兼容性和进程级强制终止恢复仍待真实凭据与环境验收。
- 阶段 4 的图片、多模态、明确 Mock 售后 Adapter、真实/模拟回执、UNKNOWN 对账、核验与 Device 可信事实归档未实现。
- 生产身份源、部署和 AWS 资源均未配置。
