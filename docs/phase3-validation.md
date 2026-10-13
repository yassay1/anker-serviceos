# 阶段 3 验证记录：真人与 Agent 共同服务

日期：2026-10-13

结论：功能代码、PostgreSQL 回归、迁移、OpenAPI/Client 一致性及前端构建已通过；`/support`、`/desk` 的部分本地浏览器路径已复验，完整业务分支仍待验收。下文“已实现”只表示对应代码和所列检查完成，不表示所有用户路径已验收。

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

2026-10-13 的前端整理后，本地浏览器使用样例身份复验：客户在 `/support` 新建会话、发送消息、刷新后恢复已保存消息，SSE 显示已连接；通过交互卡请求人工协助后，客服在 `/desk` 看到了 OPEN 任务并成功接管，随后切换到 `HUMAN_LEAD`/`HUMAN_ONLY`，任务卡随服务端版本刷新到 ASSIGNED。客服保存 INTERNAL 备注；切回客户身份后该备注不可见，客户访问 `/desk` 被拒。退出与重新登录的身份切换也已复验。前端 `npm run check:api`、`npm run typecheck`、`npm run build` 均通过。

此前浏览器曾停留在“正在确认登录状态…”；本次未稳定复现其请求未结束的根因。身份请求现有超时和失败重试界面，避免无限等待。两名客服并发领取、旧 Agent 发言策略、草稿审批拒绝、旧 UI revision 拒绝、SSE 实际断线恢复与窄屏交互的完整浏览器路径仍待逐项复验；后端回归证据见上表。

## 未实现或待真实环境验收

- 真实模型 Provider 的多轮服务、结构化工具兼容性和进程级强制终止恢复仍待真实凭据与环境验收。
- 阶段 4 的图片、多模态、明确 Mock 售后 Adapter、真实/模拟回执、UNKNOWN 对账、核验与 Device 可信事实归档未实现。
- 生产身份源、部署和 AWS 资源均未配置。
