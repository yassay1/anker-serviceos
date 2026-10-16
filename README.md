# 售后通 · Anker ServiceOS

面向智能硬件售后的持续服务系统：以服务案例承接问题，结合设备档案、证据、受控 Agent 与真人协作，并核验处理结果。

## Windows 双击体验

双击根目录 `启动体验.bat`，自动打开本机页面，启动前端热更新和可用后端。双击 `停止体验.bat` 停止本次应用服务。缺少数据库或模型时会明确显示部分能力未就绪；详细说明见[双击预览指南](docs/double-click-preview.md)。

## 工程基线

用户指定的 V1 定稿来自 `D:\proj\共享docs`，已纳入本项目。源文件哈希及本地调整见 [来源清单](docs/baseline-provenance.json)。

阅读顺序：先用本文件了解当前范围；用下列四份 V1 主基线确认产品规则和阶段目标；用验收记录核对实际完成情况。分工与接口变更见[协作开发指南](docs/contributing.md)，模块操作见[前端开发指南](frontend/README.md)和[后端与 Worker 开发指南](backend/README.md)，参考图的视觉方向见[Web 界面设计指南](docs/ui-design-guidelines.md)。

- [产品定义](docs/product-definition.md)：产品对象、协作模式、用户旅程、Agentic Interface 与性能目标。
- [系统架构](docs/architecture.md)：前后端分离、应用服务、Worker、持久化及 Agent → UI Schema → Renderer 设计。
- [领域与接口契约](docs/domain-and-contracts.md)：对象关系、状态、权限、Generative UI 数据结构与计划 API。
- [开发实施计划](docs/development-plan.md)：各阶段真实完成状态。
- [现有项目合并与归档说明](docs/baseline-integration.md)：V1 差异处理、复用边界、增量任务和验收。
- [用户表达理解与回应 Skill 设计计划](docs/emotion-understanding-response-skill.md)：基础提示指导已实现，中文售后效果评测仍待完成。
- [黑客松赛题参考资料](data/reference/hackathon/README.md)：团队共享的赛题流程与完整数据文件；不属于运行时知识库。
- [Agent 工程规则](AGENTS.md)。
- [协作开发指南](docs/contributing.md)：模块边界、契约变更、并行开发与集成检查。
- [V1 接口提案](contracts/proposed/v1/README.md)：当前真实接口与阶段 4 计划接口的统一 OpenAPI 目标；计划操作尚不可调用。
- [阶段 0 实际验收记录](docs/baseline-validation.md)：变更文件、命令、测试、浏览器结果及限制。
- [阶段 1 实际验收记录](docs/phase1-validation.md)：PostgreSQL、业务 API、权限、前端消息和范围边界。
- [阶段 2 验收记录](docs/phase2-validation.md)：Worker/Agent 落地范围、离线测试和真实 Provider 待验证项。
- [阶段 3 验收记录](docs/phase3-validation.md)：真人与 Agent 协作、持久事件、受控 UI 与本地回归结果。
- [阶段 4 模拟动作增量](docs/phase4-mock-action-validation.md)：明确标识的模拟售后请求、独立审批、Worker 回执及待完成范围。
- [阶段 4 图片界面增量](docs/phase4-image-ui-validation.md)：真实上传、检查状态、授权预览和未知上传对账。
- [阶段 4 结果状态保护](docs/phase4-resolution-guard-validation.md)：有售后动作的案例在正式核验前禁止直接标记为已解决。
- [阶段 4 结果核验增量](docs/phase4-verification-validation.md)：冻结条件、客户确认与服务端解决判定。
- [阶段 5 交付准备与集成验收](docs/phase5-validation.md)：实际执行的命令与结果、本轮修复、本机可访问的体验服务，以及仍未通过的验收门槛。
- [部署与运维手册](docs/operations.md)、[售后 SOP](docs/service-sop.md)：开发/生产依赖、迁移/备份/回滚/EC2+RDS+S3 网络与阻断说明，以及逐阶段服务流程与异常矩阵。
- [前端适配验证](docs/backend-based-frontend-validation.md)与[全面逻辑检查](docs/comprehensive-logic-audit.md)：真实接口适配、浏览器路径、恢复修复及仍待验的边界。

## 当前实现范围

阶段 1 已接入独立 PostgreSQL 业务 Schema、Alembic 迁移、开发专用登录、Conversation/Message、Service Case、Device Passport 和事实候选/核验/撤销服务。`/support` 可以建立会话并发送持久消息；`/desk` 可查看同租户会话、公开回复与内部备注。Case、Device 与 Conversation 独立，关系可多对多；消息受理同事务写入待执行 Job 和 Outbox。

旧 A1229 原型、旧功能 spec、其独立 Python 工程与历史规划记录已从活动工作区清出，并归档在同级目录 `D:\proj\Anker SreviceOS-archive-20261013`；它们不是当前运行时代码或开发入口。当前 `specs/001`–`005` 是后来按 V1 新建的活动功能切片，不沿用归档旧 spec 的任务清单。当前 Agent Runtime 使用的两份只读手册摘要已归入 `backend/serviceos_api/knowledge/`。

当前登录仅是显式启用的本地开发适配器，未接生产身份源。阶段 2 已增加独立 Worker、数据库租约/重试、AgentRun、受限 Agent Runtime 与 PostgreSQL Checkpointer；Worker 需单独启动并显式配置模型地址、模型名和 API Key。当前开发环境没有 Provider 凭据，因此真实 LLM 多轮验收尚未执行。阶段 3 已接入模式切换/审批、持久事件与 SSE 补取、受控 UI Schema/Renderer 和低风险 UI action intent；代码、PostgreSQL 回归、契约、前端构建及浏览器回归已通过，详见[阶段 3 验收记录](docs/phase3-validation.md)。阶段 4 已有图片证据、开发环境模拟售后动作、按“成功 Mock 回执＋客户确认”的结果核验、经客户同意的回访预约和到期内部客服待办，以及 Case 来源可信 Device Facts 的核验后归档与撤销。图片开发文件保存在私有本地目录而数据库仅保存对象引用；生产对象存储适配器未配置。图片限制仍待确认；结构检查不代表多模态理解或真实 Anker 接口。健康状态只表示 API 进程可响应，不代表 Worker 或模型正在运行。生产目标以 V1 为准，归档旧 spec 的 SQLite/Jinja2 方案属于历史原型。

Agentic Interface / Generative UI 已完成产品与架构设计；阶段 2 新增 Agent 的内部 `ui_proposal` 元数据和失败时文本降级。阶段 3 已实现 UIDocument、组件 Catalog、Renderer 和低风险 UI action，并通过本地代码与契约检查；浏览器交互仍有上述待复验项。内部提案不等于用户可见界面，只有发布后的受信 UIDocument 才可渲染。

本地 Agent 初始化（仅在已选择并获准使用模型 Provider 后）：先从仓库根目录执行 `uv run --project backend alembic -c backend/alembic.ini upgrade head`，再执行 `uv run --project backend python -m serviceos_api.checkpoints` 初始化独立的 `serviceos_checkpoint` schema；另开终端运行 `uv run --project backend python -m serviceos_api.worker.main`。API 启动不会自动迁移、创建 Checkpointer 表或启动 Worker。未配置 Provider 时，Worker 在领取任何 Job 前拒绝启动。

## 目录

```text
docs/                     V1 主基线、来源与增量合并计划
frontend/                 单一 Web 应用：用户服务与客服视图
backend/serviceos_api/    新 FastAPI 包；业务模型、应用服务与 HTTP API
backend/migrations/       独立 PostgreSQL 业务 Schema 的 Alembic 迁移
contracts/openapi.json   从实际 API 代码生成
contracts/proposed/v1/    前后端协作用的完整 V1 接口提案；planned 操作未实现
backend/serviceos_api/knowledge/ Agent 只读本地手册资料
data/reference/hackathon/  团队共享的赛题参考资料（不随应用打包）
.agents/skills/           开发工作流 Skill，与业务 Skill 分离
.specify/                 Spec Kit 工作流、模板与工程宪章
specs/                    按 V1 新建的活动功能切片
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

若本机已有开发容器，使用现有容器并确认端口与 `backend/.env` 一致。`.env.example` 中的账号密码只是本地样例，不可用于生产。随后在项目根目录显式迁移并初始化本地测试身份：

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
- 存活接口：`http://127.0.0.1:8000/api/v1/health`
- 就绪接口：`http://127.0.0.1:8000/api/v1/readiness`（分别报告数据库、Schema、身份、Provider 与存储，并在未就绪时返回 503；不泄露连接信息）
- 实际 API 文档：`http://127.0.0.1:8000/docs`

图片检查、模拟动作、回访与事件派发都不需要模型配置，可各自单独启动：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.inspection
uv run --project backend --locked python -m serviceos_api.worker.actions
uv run --project backend --locked python -m serviceos_api.worker.followups
uv run --project backend --locked python -m serviceos_api.worker.outbox
```

这些进程会定期写入心跳文件，容器健康检查与本地排查使用同一条命令：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.health --role inspection
```

`python -m serviceos_api.worker.main`（Agent 主 Worker）需要显式配置 `SERVICEOS_LLM_MODEL`、`SERVICEOS_LLM_BASE_URL` 和 `SERVICEOS_LLM_API_KEY`，未配置时立即退出，不领取任务也不生成回复。

需要可复现的容器化环境时，使用仓库根的 Compose 说明与运维手册，而不是手工拼装进程。

Vite 将 `/api` 代理到本地 API，开发服务均绑定回环地址。体验登录身份有 `customer-a`、`customer-b`、`staff`、`other-tenant`，密码使用 `.env` 的 `SERVICEOS_LOCAL_AUTH_PASSWORD`。浏览器只显示真实保存的消息与权限范围；未配置 Provider 时不会运行自动回复。

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
uv run --project backend --locked python -m serviceos_api.export_openapi
cd frontend
npm run generate:api
```

当前活动后端工程、依赖和测试均位于 `backend/`；根目录不再保留第二套 Python 工程或旧原型测试入口。归档中的旧原型测试仅是历史资产，不属于当前 CI 或活动验收范围。

含团队私人联系方式的预赛材料已移出工作区，放在上述项目外归档目录的 `private/` 子目录；分享/公开归档前仍需按隐私要求单独审查。本目录已推送到私有 Git 仓库；`.github/workflows/ci.yml` 已配置，远端运行结果以 GitHub Actions 的实际记录为准。
