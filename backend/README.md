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

API 不会自动执行数据库迁移、初始化 LangGraph Checkpointer 或启动 Worker。主 Agent 与诊断专家共用 `SERVICEOS_LLM_MODEL`、`SERVICEOS_LLM_BASE_URL`、`SERVICEOS_LLM_API_KEY` 和超时配置。确认模型目的地已经获准使用；OpenAI-compatible Provider 若有额外请求参数，可用 `SERVICEOS_LLM_EXTRA_BODY_JSON` 设置 JSON 对象。DeepSeek 官方 Chat Completions 在未显式配置 thinking 参数时会自动关闭 thinking，以兼容结构化 Agent 输出所需的强制工具调用。再从仓库根目录执行：

```powershell
uv run --project backend --locked python -m serviceos_api.checkpoints
uv run --project backend --locked python -m serviceos_api.worker.main
```

Worker 使用独立的 `serviceos_checkpoint` schema 保存执行检查点；业务数据仍以 PostgreSQL 业务 schema 为准。缺少 Provider 配置时 Worker 不领取任务。真实模型多轮和进程强制中断恢复的验收状态见[阶段 2 验收记录](../docs/phase2-validation.md)。

富内容是原消息 `content[].rich` 的可选只读扩展；旧文本仍保留，快捷追问仍调用原消息 API，并通过 `reply_to_message_id` 拒绝过期追问。只在已选择支持图像输入的 Provider 后设置 `SERVICEOS_LLM_VISION=1`：同一 Agent 可读取一张已授权、检查通过且不超过 2 MiB 的图片。未开启、图片不可读或定位不可靠时保留文本/原图，不声称已完成视觉诊断；当前不自动裁切未经核验的区域。

图片证据的结构检查使用另一个进程，不读取模型配置，也不代表病毒扫描或真实 Anker 接口：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.inspection
```

隔离验收可在命令末尾加 `--once`，只处理当前一条待检查记录后退出。

不需要模型配置的四个进程（图片检查、模拟动作、回访、事件派发）都会定期写心跳，容器健康检查与本地排查用同一条命令：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.health --role inspection
```

`--role` 取 `inspection`、`actions`、`followups`、`outbox`、`agent`；每个 worker 模块里的 `ROLE` 常量是唯一来源，`compose.yaml` 的健康检查角色与该常量必须一致（有回归测试）。心跳文件位于系统临时目录，默认 120 秒内无成功轮询即视为不健康。

未检查通过的图片不能下载。已配置 Provider 的消息 Worker 在领取对话任务之余也会领取图片检查任务；未配置时它仍然在领取任何对话任务前退出。
开发环境的图片原文保存在私有 `backend/.data/evidence/`，数据库只保存元数据和对象引用。API 与图片检查 Worker 必须使用同一个本地目录；需要放在别处时，在两个进程的环境中设置相同的绝对路径 `SERVICEOS_EVIDENCE_STORAGE_DIR`。生产对象存储适配器尚未配置，图片证据接口在生产配置下返回不可用，不会静默写入进程本地磁盘。

模拟售后动作使用独立 Worker，不需要模型 Provider。客服申请后由另一名主管或管理员审批；在开发环境可用 `supervisor` 样例账号体验。审批不会执行动作，Worker 才会向持久的 Mock Adapter 提交并保存带 `MOCK` 标识的回执。`UNKNOWN` 只按原动作编号查询对账，不重复提交：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.actions
```

`--once` 只处理一条待执行记录，供受控联调使用。`SERVICEOS_MOCK_ACTION_RESULT=FAILED` 可在开发环境演示模拟失败；默认 `SUCCEEDED`。生产配置不启用该 Adapter，模拟动作 API 返回不可用；这些回执不是 Anker 真实操作结果。动作语义和审批角色已由用户确认，范围见[功能契约](../specs/007-mock-service-action/contracts/feature-contract.md)。

结果核验按已确认的[功能契约](../specs/008-resolution-verification/contracts/feature-contract.md)执行：每个模拟动作有冻结条件，只有成功 Mock 回执加客户本人明确确认，Case 才进入 `RESOLVED`。客服可读核验记录，但不能代客户确认；旧 Case 状态接口仍拒绝绕过。核验路由与模拟动作一样只在开发/测试环境提供。

客户同意回访后，客服才能在关联会话的 Case 下预约同一目的的一次回访。到期提醒进程只创建分配给预约客服的内部任务，不发送客户消息，也不需要模型配置：

```powershell
uv run --project backend --locked python -m serviceos_api.worker.followups
```

`--once` 仅检查并处理一条到期记录，供受控联调。这个进程需与 API 连接同一业务数据库；未启动时预约仍保留为 `SCHEDULED`，不会虚报已提醒。

设备事实仍使用现有候选、客服核验和撤销应用服务。新增 Case 来源编号必须指向同客户且已关联的设备；客服仅能把已核验、来源 Case 已解决的事实归档到长期 Device Passport。归档前的 Case 来源事实不会进入客户或 Agent 的可信事实视图，撤销后也会退出该视图。历史无 Case 来源的已核验事实沿用原有显示规则。

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
uv run --project backend --locked ruff check backend/serviceos_api backend/tests
uv run --project backend --locked pytest backend/tests --require-postgres
uv run --project backend --locked python -m serviceos_api.export_openapi --check
```

Ruff F821/F823 检查活动后端源码和测试中的未定义名称与未绑定局部变量；评测数据、文档和归档不在扫描范围内。

跨模块功能先由前后端核对[V1 接口提案](../contracts/proposed/v1/README.md)，按[协作开发指南](../docs/contributing.md)共同确认[拟定功能契约](../docs/templates/feature-contract.md)，再并行实现。接口由真实路由、Pydantic Schema 和应用服务实现后才导出 `contracts/openapi.json`；前端再生成 `src/api/schema.d.ts`。开发计划和阶段验收记录决定完成状态；工作区中的代码、草案或测试替身不自动构成已交付能力。

新路由模块必须在 `serviceos_api/main.py` 注册：`tests/test_api_baseline.py` 会遍历 `serviceos_api.api` 下的每个路由模块，断言其全部路径都出现在真实应用的 OpenAPI 里。只在测试里自行组装应用的路由，等于未发布接口。

`GET /api/v1/skills` 与 `GET /api/v1/conversations/{id}/skill-executions` 只对同租户客服开放（客户 403、跨租户 404），执行记录为仅内部可见的有界分页。Skill 是固定版本的服务方法，不是可执行的远程代码；`emotion-assessment` 当前为 `PREPARED`，不产生情绪判断，也不得据此自动退款、换货、关单或改变协作模式。运行手册见[部署与运维](../docs/operations.md)，逐环节服务规则见[售后 SOP](../docs/service-sop.md)。

`/api/v1/experience-candidates` 是客服内部的经验候选审核 API：仅 `VERIFIED_RESOLVED` 生成空候选，客服整理，主管/管理员审核。Approved 经验只作为有来源的内部参考注入 Agent context；不修改 DeviceFact/Skill，也不包含客户原始文本。状态、复用过滤与实现限制见[经验沉淀验收记录](../docs/experience-learning-validation.md)。
