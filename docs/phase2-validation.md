# 阶段 2：Worker 与受控 Agent Runtime 验收记录

日期：2026-10-13。范围仅限 `docs/development-plan.md` 阶段 2；阶段 3 真人协作台和阶段 4 外部业务动作未实施。旧 `app/` 原型、规格历史和共享基线源文件均保留。

> 清理说明：本文上句反映阶段 2 验收时的状态。2026-10-13 随后的工作区清理已将旧 A1229 原型和旧功能 spec 归档到项目外；共享基线源文件仍保持不变。

## 实际落地

- `backend/serviceos_api/worker/runtime.py`：Job 与 Outbox 使用 PostgreSQL `FOR UPDATE SKIP LOCKED`、租约令牌、心跳、租约过期恢复、同会话串行领取、指数退避、最大尝试数、失败终态/Outbox dead-letter。Conversation dispatcher 只确认写入会话事件表的事件；没有 Conversation 路由的 Outbox 事件保持未确认，等待对应消费者。
- `backend/serviceos_api/agents/runtime.py`：配置显式模型名、API Key 和 Base URL 后才建立 LangChain `create_agent`；设置请求超时、最多 6 次模型调用、最多 12 次工具调用、单次最多 1000 输出 token。每个新回合以受权业务上下文重建短期状态；同一回合检查 checkpoint 标识并复用已完成结果，未完成节点可继续恢复。
- `backend/serviceos_api/application/agent_services.py`：只装载当前租户/会话/客户可关联案例和设备；仅提供最近公开消息、已关联案例、已核验设备事实。内部消息、候选设备事实、设备序列号不进入 Agent 上下文；未核验型号明确作为 reported data。
- Agent 工具只读本地诊断 SOP，或创建幂等的内部证据/动作草稿；这些草稿不是对客消息、已核验事实或外部动作。
- `ConversationService.publish_agent_response` 重新读取会话并加锁：仅 `AI_LEAD + AI_AUTO` 可公开回复；其他策略只保存 INTERNAL；AgentRun ID 同时用作幂等消息键。
- Alembic `0003_agent_worker_runtime` 与 `0004_outbox_dead_letter` 增加租约、重试、AgentRun、内部提案、持久会话事件和 Outbox dead-letter 数据。Checkpoint 表单独在 `serviceos_checkpoint` schema，通过 `python -m serviceos_api.checkpoints` 显式初始化。
- Worker 使用 `python -m serviceos_api.worker.main` 独立启动；API 进程不迁移数据库、不启动 Worker、不自动初始化 Checkpointer。

## 验证结果

- 后端真实 PostgreSQL 集成测试：`45 passed`。覆盖迁移往返、Job 领取/租约过期重领与令牌 fencing、同会话串行、失败脱敏/退避/终态、未配置 Provider 不领取任务、Outbox 幂等/dead-letter/未路由事件不误确认、上下文隐私过滤、成功回复经 ConversationService 入库及 HUMAN_LEAD 策略不公开。
- 开发库迁移：`uv run --project backend alembic -c backend/alembic.ini upgrade head` 成功；`... alembic check` 输出 `No new upgrade operations detected.`
- Checkpointer 初始化：`python -m serviceos_api.checkpoints` 成功；检查到 `serviceos_checkpoint` 下 `checkpoints`、`checkpoint_blobs`、`checkpoint_writes`、`checkpoint_migrations` 四张表，与业务 `serviceos` schema 分离。
- 原型回归：`uv run --project . pytest tests -q -p no:cacheprovider`：`1 passed`。
- API 合同与前端：OpenAPI 与 FastAPI 应用一致；生成的 API 类型一致；前端 `tsc --noEmit` 和 Vite production build 通过。
- 后端依赖锁：`uv lock --project backend --check` 通过。

## 未完成/风险边界

- `backend/.env` 只配置本地数据库/开发身份，没有模型 Provider 的 model/base URL/API Key。Worker 会在领取消息前退出，未发送模型请求、未产生外部 Provider 成本；真实模型、多轮服务质量、目标 Provider 的工具协议兼容性尚未验收。
- 代码有 lease/checkpoint 恢复路径并通过租约过期测试，但没有真实模型执行中的强制杀进程/重启演示。真实 Agent 工具、副作用交互需在 Provider 配置后补充端到端验收。
- 当前没有 SSE/事件查询 API；Outbox 已可靠写入 `conversation_events`，但面向前端的补取与可见性过滤属于阶段 3。
- token 约束是每次模型输出上限与总模型调用上限，形成输出 token 总量硬上界；不同 OpenAI-compatible Provider 的实际 tokenizer/input usage 统计尚未实测，不能视为严格的全程输入 token 精算预算。
- 项目目录没有 `.git`，本记录不提供 Git diff 或提交哈希，也未初始化 Git。

## 2026-10-13 阶段 2 剩余项增量验收

独立切片为 [Agent 结果分离](../specs/001-agent-result-separation/spec.md)。本节记录后续增量，不改写上方历史验收的环境和结果。`AgentRuntime` 现在解析独立文本与可选受限 UI 提案；无效 UI 只留下 `ui_proposal_invalid` 原因码，文本保留。动作引用由同租户、同 Run 的内部 `ACTION` 草稿查询生成，模型最终回答不能直接制造动作。`AgentRun.result_payload` 经迁移 `0005_agent_result` 保存分离结果。Worker 和工具写入均复核当前 Job 租约；公开文本仍由 Conversation Service 复核最新策略。

本次使用现有本地 PostgreSQL 17 容器。命令及结果：

| 命令 | 结果 |
|---|---|
| `uv run --project backend --locked pytest backend/tests --require-postgres -q`（设置 `SERVICEOS_TEST_DATABASE_URL`） | `57 passed`；含结果解析、UI 降级、内部动作幂等、恢复复用、HUMAN_LEAD 和租约拒绝 |
| `uv run --project backend --locked alembic -c backend/alembic.ini upgrade head` | 开发库升级到 `0005_agent_result` |
| `uv run --project backend --locked alembic -c backend/alembic.ini check` | `No new upgrade operations detected.` |
| `uv run --project backend --locked python -m serviceos_api.export_openapi --check` | 与应用一致；本切片没有新增 HTTP 路由 |
| `npm run check:api`、`npm run typecheck`、`npm run build` | 类型与构建通过；无虚构 UI 接口 |

真实 Provider 多轮、目标 Provider 的 JSON/工具协议兼容性和真实模型运行中的强制杀进程恢复仍待凭据后验收。当前 PostgreSQL 测试替身只验证本地逻辑，不表示上述三项通过。阶段 3 的 UIDocument、Catalog、Renderer、UI action 和 SSE 未实现。

## 2026-10-15 Agent Harness V2 增量

- `AgentContextBuilder` 采用分层的结构化上下文及 6,000 token 估算预算，优先保留协作策略、关联 Case 状态、可信设备事实和当前用户问题；较新公开消息按剩余预算保留，较早公开消息形成最多 30 条带来源 ID/说话者/时间的摘录记忆，存入既有 `AgentRun.result_payload.context_memory`。内部消息不进入记忆；摘要不提升事实核验状态。上下文长度超过预算时依固定优先级裁剪历史和次要状态。
- 上下文还包含关联文本 Evidence、公开图片的检查/核验元数据、动作与审批状态、结果核验、未关闭任务及 Follow-up。图片上下文不含图片字节或存储 key，也不声称模型已观察图片内容。
- 新 AgentRun 使用独立 LangGraph `thread_id`；旧 Run 仍沿用其已保存的 `thread_id`，用于部署期间兼容恢复。业务会话记忆从业务数据库重新装配，Checkpoint 仍只保存执行状态。
- LangChain `SummarizationMiddleware` 在约 16,000 个估算消息 token 时对单次运行压缩，保留最近 8 条消息；使用售后专用摘要指令，不允许压缩内容形成已核验事实。`lookup_manual` 对本地资料按 query 排序，只有设备型号已核验为 A1229 时才返回 A1229 专属资料；回执包含文件哈希版本和适用范围。现有固定版本 Skill 仍按需加载，Skill 执行不扩充工具授权。
- AgentRun 内部结果补充上下文构建耗时/估算 token、摘要与历史数量、每轮模型 token 汇总和按名称统计的工具调用次数，不记录工具参数或原始推理内容。

本机验证：

| 命令 | 结果 |
|---|---|
| `uv run --project backend --locked pytest backend/tests/test_agent_context_helpers.py backend/tests/test_worker_runtime.py backend/tests/test_skills.py backend/tests/test_agent_result.py -q` | `41 passed, 40 skipped`；当前环境未配置 `SERVICEOS_TEST_DATABASE_URL`，PostgreSQL 集成用例未执行 |
| `uv run --project backend --locked python -m compileall -q backend/serviceos_api backend/tests` | 通过 |
| `git diff --check` | 通过 |

以上不验证真实模型行为、Provider 的工具协议、Token 估算精度或数据库集成路径。新增上下文连续性和 Case/权限查询仍需在配置隔离 PostgreSQL 的环境中运行；真实 Provider 多轮与强制终止恢复仍待凭据后验收。
