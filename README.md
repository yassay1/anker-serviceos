# 售后通 · Anker ServiceOS

面向智能硬件售后的持续服务系统：以服务案例承接问题，结合设备档案、证据、受控 Agent 与真人协作，并核验处理结果。

## 工程基线

用户指定的 V1 定稿来自 `D:\proj\共享docs`，已纳入本项目。源文件哈希及本地调整见 [来源清单](docs/baseline-provenance.json)。

- [产品定义](docs/product-definition.md)：产品对象、协作模式、用户旅程、Agentic Interface 与性能目标。
- [系统架构](docs/architecture.md)：前后端分离、应用服务、Worker、持久化及 Agent → UI Schema → Renderer 设计。
- [领域与接口契约](docs/domain-and-contracts.md)：对象关系、状态、权限、Generative UI 数据结构与计划 API。
- [开发实施计划](docs/development-plan.md)：各阶段真实完成状态。
- [现有项目合并与归档说明](docs/baseline-integration.md)：V1 差异处理、复用边界、增量任务和验收。
- [Agent 工程规则](AGENTS.md)。
- [阶段 0 实际验收记录](docs/baseline-validation.md)：变更文件、命令、测试、浏览器结果及限制。
- [阶段 1 实际验收记录](docs/phase1-validation.md)：PostgreSQL、业务 API、权限、前端消息和范围边界。
- [阶段 2 验收记录](docs/phase2-validation.md)：Worker/Agent 落地范围、离线测试和真实 Provider 待验证项。

## 当前实现范围

阶段 1 已接入独立 PostgreSQL 业务 Schema、Alembic 迁移、开发专用登录、Conversation/Message、Service Case、Device Passport 和事实候选/核验/撤销服务。`/support` 可以建立会话并发送持久消息；`/desk` 可查看同租户会话、公开回复与内部备注。Case、Device 与 Conversation 独立，关系可多对多；消息受理同事务写入待执行 Job 和 Outbox。

旧 A1229 原型、旧功能 spec、其独立 Python 工程与历史规划记录已从活动工作区清出，并归档在同级目录 `D:\proj\Anker SreviceOS-archive-20261013`；它们不是当前运行时代码或开发入口。旧 spec 需要重新设计，不应继续按旧任务清单实施。当前 Agent Runtime 使用的两份只读手册摘要已归入 `backend/serviceos_api/knowledge/`。

当前登录仅是显式启用的本地开发适配器，未接生产身份源。阶段 2 已增加独立 Worker、数据库租约/重试、AgentRun、受限 Agent Runtime 与 PostgreSQL Checkpointer；Worker 需单独启动并显式配置模型地址、模型名和 API Key。当前开发环境没有 Provider 凭据，因此真实 LLM 多轮验收尚未执行。模式切换/审批、SSE、外部动作执行和核验闭环仍属后续阶段。健康状态只表示 API 进程可响应，不代表 Worker 或模型正在运行。生产目标以 V1 为准，旧 `specs/` 的 SQLite/Jinja2 方案属于历史原型。

Agentic Interface / Generative UI 已完成产品与架构设计，但当前没有 UI Schema、组件 Catalog、Renderer 或 UI action API；设计不等于已实现能力。

本地 Agent 初始化（仅在已选择并获准使用模型 Provider 后）：先从仓库根目录执行 `uv run --project backend alembic -c backend/alembic.ini upgrade head`，再执行 `uv run --project backend python -m serviceos_api.checkpoints` 初始化独立的 `serviceos_checkpoint` schema；另开终端运行 `uv run --project backend python -m serviceos_api.worker.main`。API 启动不会自动迁移、创建 Checkpointer 表或启动 Worker。未配置 Provider 时，Worker 在领取任何 Job 前拒绝启动。

## 目录

```text
docs/                     V1 主基线、来源与增量合并计划
frontend/                 单一 Web 应用：用户服务与客服视图
backend/serviceos_api/    新 FastAPI 包；业务模型、应用服务与 HTTP API
backend/migrations/       独立 PostgreSQL 业务 Schema 的 Alembic 迁移
contracts/openapi.json   从实际 API 代码生成
backend/serviceos_api/knowledge/ Agent 只读本地手册资料
.agents/skills/           开发工作流 Skill，与业务 Skill 分离
.specify/                 Spec Kit 工作流、模板与工程宪章；活动功能 spec 尚未重建
.github/workflows/        基础校验与契约一致性 CI
```

顶层 `knowledge/`、`infra/` 等目录随真实功能建立；当前 Runtime 手册位于 `backend/serviceos_api/knowledge/`。

## 本地启动

支持 Python 3.12、Node 24；使用 uv 与 npm 锁文件。当前工程在 Python 3.12.14 / Node 24.16.0 下验证。

先准备 PostgreSQL 17 和本地开发配置。若是本机首次运行，可创建一个仅回环开放的开发容器：

```powershell
docker run --name serviceos-postgres-local -e POSTGRES_DB=serviceos_dev -e POSTGRES_USER=serviceos_local -e POSTGRES_PASSWORD=serviceos_local_only -p 127.0.0.1:55432:5432 -v serviceos-postgres-local-data:/var/lib/postgresql/data -d postgres:17
Copy-Item backend/.env.example backend/.env
```

当前开发机已建有相同配置的 `serviceos-v1-postgres-20261012` 容器；重启时用 `docker start serviceos-v1-postgres-20261012`，不要再次运行上面的创建命令。`.env.example` 中的账号密码只是本地样例，不可用于生产。随后在项目根目录显式迁移并初始化本地测试身份：

```powershell
uv sync --project backend --locked
uv run --project backend --locked alembic -c backend/alembic.ini upgrade head
uv run --project backend --locked python -m serviceos_api.bootstrap_local
```

启动 API：

```powershell
uv run --project backend --locked uvicorn serviceos_api.main:app --host 127.0.0.1 --port 8000
```

另开终端启动 Web：

```powershell
cd frontend
npm ci
npm run dev
```

- 用户入口：`http://127.0.0.1:5173/support`
- 客服入口：`http://127.0.0.1:5173/desk`
- 健康接口：`http://127.0.0.1:8000/api/v1/health`
- 实际 API 文档：`http://127.0.0.1:8000/docs`

Vite 将 `/api` 代理到本地 API，开发服务均绑定回环地址。体验登录身份有 `customer-a`、`customer-b`、`staff`、`other-tenant`，密码使用 `.env` 的 `SERVICEOS_LOCAL_AUTH_PASSWORD`。浏览器只显示真实保存的消息与权限范围，自动回复尚未运行。

## 校验与契约生成

根目录执行：

```powershell
$env:SERVICEOS_TEST_DATABASE_URL='postgresql+psycopg://serviceos_local:serviceos_local_only@127.0.0.1:55432/serviceos_dev'
uv run --project backend --locked pytest backend/tests --require-postgres
uv run --project backend --locked python -m serviceos_api.export_openapi --check
```

`frontend/` 下执行：

```powershell
npm run check:api
npm run typecheck
npm run build
```

API 发生实际变化后，在根目录导出，再在 `frontend/` 生成 Client 类型：

```powershell
uv run --project backend python -m serviceos_api.export_openapi
cd frontend
npm run generate:api
```

当前活动后端工程、依赖和测试均位于 `backend/`；根目录不再保留第二套 Python 工程或旧原型测试入口。归档中的旧原型测试仅是历史资产，不属于当前 CI 或活动验收范围。

含团队私人联系方式的预赛材料已移出工作区，放在上述项目外归档目录的 `private/` 子目录；分享/公开归档前仍需按隐私要求单独审查。此目录尚未初始化 Git；CI 文件本地可审阅，但未在远端运行。
