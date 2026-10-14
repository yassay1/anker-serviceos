# API 与 Worker 开发指南

本目录是售后通的 Python 3.12 后端工程。FastAPI 与 Worker 使用同一业务应用服务，但作为独立进程运行。产品对象和权限以[四份 V1 基线](../README.md#工程基线)为准；全栈启动入口见[仓库 README](../README.md)。

## 本地依赖与启动

准备 PostgreSQL 17、本地 `backend/.env` 和开发身份。变量名称与本地样例见 [`.env.example`](.env.example)，真实密钥只放本地环境，不提交。仓库根目录执行：

```powershell
if (-not (Test-Path -LiteralPath backend/.env)) { Copy-Item backend/.env.example backend/.env }
uv sync --project backend --locked
uv run --project backend --locked alembic -c backend/alembic.ini upgrade head
uv run --project backend --locked python -m serviceos_api.bootstrap_local
uv run --project backend --locked uvicorn serviceos_api.main:app --host 127.0.0.1 --port 8000
```

已有 `.env` 时核对配置并保留现有文件。数据库容器的本地创建示例在[仓库 README](../README.md#本地启动)。API 文档在 `http://127.0.0.1:8000/docs`，健康接口在 `/api/v1/health`；健康接口只说明 API 进程可响应。

## Agent Worker

API 不会自动执行数据库迁移、初始化 LangGraph Checkpointer 或启动 Worker。需要运行 Agent 时，先显式配置 `SERVICEOS_LLM_MODEL`、`SERVICEOS_LLM_BASE_URL` 和 `SERVICEOS_LLM_API_KEY`，确认模型目的地已经获准使用，再从仓库根目录执行：

```powershell
uv run --project backend --locked python -m serviceos_api.checkpoints
uv run --project backend --locked python -m serviceos_api.worker.main
```

Worker 使用独立的 `serviceos_checkpoint` schema 保存执行检查点；业务数据仍以 PostgreSQL 业务 schema 为准。缺少 Provider 配置时 Worker 不领取任务。真实模型多轮和进程强制中断恢复的验收状态见[阶段 2 验收记录](../docs/phase2-validation.md)。

图片证据的结构检查使用另一个进程，不读取模型配置，也不代表病毒扫描或真实 Anker 接口：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.inspection
```

隔离验收可在命令末尾加 `--once`，只处理当前一条待检查记录后退出。

未检查通过的图片不能下载。已配置 Provider 的消息 Worker 在领取对话任务之余也会领取图片检查任务；未配置时它仍然在领取任何对话任务前退出。
开发环境的图片原文保存在私有 `backend/.data/evidence/`，数据库只保存元数据和对象引用。API 与图片检查 Worker 必须使用同一个本地目录；需要放在别处时，在两个进程的环境中设置相同的绝对路径 `SERVICEOS_EVIDENCE_STORAGE_DIR`。生产对象存储适配器尚未配置，图片证据接口在生产配置下返回不可用，不会静默写入进程本地磁盘。

模拟售后动作使用独立 Worker，不需要模型 Provider。客服申请后由另一名主管或管理员审批；在开发环境可用 `supervisor` 样例账号体验。审批不会执行动作，Worker 才会向持久的 Mock Adapter 提交并保存带 `MOCK` 标识的回执。`UNKNOWN` 只按原动作编号查询对账，不重复提交：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.actions
```

`--once` 只处理一条待执行记录，供受控联调使用。`SERVICEOS_MOCK_ACTION_RESULT=FAILED` 可在开发环境演示模拟失败；默认 `SUCCEEDED`。生产配置不启用该 Adapter，模拟动作 API 返回不可用；这些回执不是 Anker 真实操作结果。动作语义和审批角色已由用户确认，范围见[功能契约](../specs/007-mock-service-action/contracts/feature-contract.md)。

结果核验按已确认的[功能契约](../specs/008-resolution-verification/contracts/feature-contract.md)执行：每个模拟动作有冻结条件，只有成功 Mock 回执加客户本人明确确认，Case 才进入 `RESOLVED`。客服可读核验记录，但不能代客户确认；旧 Case 状态接口仍拒绝绕过。核验路由与模拟动作一样只在开发/测试环境提供。

## 代码边界

| 位置 | 职责 |
|---|---|
| `serviceos_api/api/` | HTTP 路由、认证依赖和响应 |
| `serviceos_api/application/` | 类型化契约、授权、业务状态与发布规则 |
| `serviceos_api/persistence/`、`migrations/` | SQLAlchemy 模型、业务 schema 与 Alembic 迁移 |
| `serviceos_api/agents/`、`worker/` | 受限 Agent Runtime、持久任务领取、重试与恢复 |
| `serviceos_api/knowledge/` | 当前 Runtime 使用的只读本地手册 |
| `tests/` | API、领域、数据库与 Worker 回归 |

Agent 工具通过应用服务提交业务命令；公开消息和事件由 Conversation Service 按最新权限发布。Device Passport、Service Case、Conversation 与 Agent Run 各自独立。完整边界见[系统架构](../docs/architecture.md)及[协作开发指南](../docs/contributing.md)。

## 测试与接口发布

集成测试会基于 `SERVICEOS_TEST_DATABASE_URL` 创建并删除独立测试数据库。先确认它指向本地测试 PostgreSQL，随后从仓库根目录执行：

```powershell
$env:SERVICEOS_TEST_DATABASE_URL='postgresql+psycopg://serviceos_local:serviceos_local_only@127.0.0.1:55432/serviceos_dev'
uv run --project backend --locked pytest backend/tests --require-postgres
uv run --project backend --locked python -m serviceos_api.export_openapi --check
```

跨模块功能先由前后端核对[V1 接口提案](../contracts/proposed/v1/README.md)，按[协作开发指南](../docs/contributing.md)共同确认[拟定功能契约](../docs/templates/feature-contract.md)，再并行实现。接口由真实路由、Pydantic Schema 和应用服务实现后才导出 `contracts/openapi.json`；前端再生成 `src/api/schema.d.ts`。开发计划和阶段验收记录决定完成状态；工作区中的代码、草案或测试替身不自动构成已交付能力。
