# 阶段 1 验收记录：业务底座 D101–D105

> 本文记录阶段 1 完成当时的真实状态。2026-10-13 工作区清理后，旧 A1229 原型目录、旧 spec 与根级原型测试已归档到项目外；下文的原型回归与文件哈希结果仍是当时的历史验收证据。

日期：2026-10-12。依据用户指定的 `D:\proj\共享docs` V1 定稿和本项目 [合并计划](baseline-integration.md) 实施。本记录只确认阶段 1；整个售后通仍有阶段 2–5。

## 本次实际改动

| 范围 | 文件/目录 | 已实现 |
|---|---|---|
| PostgreSQL | `backend/serviceos_api/persistence/`、`backend/migrations/`、`backend/alembic.ini`、`backend/pyproject.toml`、`backend/uv.lock` | 独立 `serviceos` 业务 Schema；两版 Alembic 迁移；租户复合外键、版本/状态/事实约束；不在 API 启动时自动建表 |
| 业务写入 | `backend/serviceos_api/application/` | Case、Device、Conversation 独立；Case–Device 与 Case–Conversation 多对多；案例状态留痕；事实候选、人工核验、撤销；消息经 ConversationService 幂等写入，Message、待执行 Job、Outbox 同一事务提交 |
| 身份与 HTTP | `backend/serviceos_api/api/`、`settings.py`、`bootstrap_local.py`、`main.py`、`backend/.env.example` | 显式启用的本地体验身份；随机会话令牌只存哈希；客户、客服、租户和可见性检查；生产默认未配置身份时拒绝；业务路由和错误状态真实返回 |
| Web 与契约 | `frontend/src/`、`contracts/openapi.json` | 从实际 FastAPI 生成 OpenAPI/TS 类型；用户会话创建、发送、回执、刷新恢复；客服公开回复与内部备注；失败保留原消息标识重试；窄屏布局 |
| 质量与说明 | `backend/tests/`、`.github/workflows/ci.yml`、`README.md`、`docs/` | 真 PostgreSQL 集成测试、CI PostgreSQL 服务、本地启动说明与阶段勾选 |

原 `app/`、`tests/`、`specs/`、`.specify/`、`service_skills/`、`service_capabilities/` 的 94 个原始文件与先前 SHA-256 快照逐一一致；`D:\proj\共享docs` 五份定稿的哈希也保持一致。未迁移、覆盖或删除这些资产。

## 实际验收

本机使用独立的 PostgreSQL 17.11 开发容器 `serviceos-v1-postgres-20261012`，只发布 `127.0.0.1:55432`。开发数据库 `serviceos_dev` 已升级到 `0002_reliable_intake` 并显式建立本地测试身份。集成测试每次创建仅属于本次测试的随机 `serviceos_test_*` 数据库，结束后只删除该数据库，不重建开发库。

| 检查 | 执行命令/方式 | 结果 |
|---|---|---|
| PostgreSQL API 与领域测试 | `uv run --project backend --locked pytest backend/tests --require-postgres -q`，设置 `SERVICEOS_TEST_DATABASE_URL` | 35 passed；涵盖迁移往返、无设备 Case、多对多、跨租户复合外键、认证/过期/撤权、内部备注隔离、状态流转、事实候选核验撤销、并发幂等、消息与 Job/Outbox 失败回滚 |
| 原型回归 | `uv run --locked pytest tests -q` | 1 passed |
| 模型与迁移一致 | `uv run --project backend --locked alembic -c backend/alembic.ini check` | No new upgrade operations detected |
| HTTP 契约 | `uv run --project backend --locked python -m serviceos_api.export_openapi --check` | 与实际 API 一致 |
| 前端类型与构建 | `npm run check:api`、`npm run build` | 生成类型一致；TypeScript 与 Vite 构建通过 |
| 浏览器路径 | 本地 `/support` 和 `/desk` | 客户登录→新建会话→发送→刷新仍显示；客服读同一会话并写内部备注；切回客户时备注不显示；退出与切换身份立即生效；390px 宽度布局可用 |

测试环境曾显示一条 Starlette `TestClient` 的 `httpx` 弃用提醒；不影响本次 35 项通过结果。CI 文件已增加 PostgreSQL 服务，但此目录仍不是 Git 仓库，无法声称远端 CI 已运行。

## 已实现边界与下一阶段

- 当前 `202` 表示消息、待执行任务与 Outbox 已持久提交；没有 Worker 消费任务，也没有真实 LLM 回复。页面明确标出这一状态。
- 本地账号只用于开发/测试；默认生产配置拒绝业务认证。生产身份源、部署密钥、会话管理和正式登录流程未实施。
- `DeviceFact` 只有人工明确核验后才出现在用户的 `verified_facts` 中；候选事实不会因消息或模型提取自动晋升。自动知识抽取、核验业务凭据与外部设备核验仍在后续阶段。
- `/desk` 已有基本会话读取、公开回复和内部备注；分配、模式切换、审批、SSE 和双人接管冲突属于阶段 3。
- 阶段 2 应先为已入库的 MessageJob/Outbox 建立可恢复 Worker、租约、重试与审计，再接入真实 `create_agent`、PostgreSQL Checkpointer、Context Builder 和受控工具。旧原型的 Jev、Skill、Provider Adapter、验证规则需经应用服务逐项复用。
