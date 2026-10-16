# 调研记录：Visible Specialist Orchestration

**状态**：已批准的实现依据；当前是否落地以实际代码和验收记录为准。**核对日期**：2026-10-16。

## 实施前仓库基线（历史快照，勿当作当前状态）

- 依赖范围见 `backend/pyproject.toml`，锁定版本见 `backend/uv.lock`：LangChain 1.4.5、langchain-core 1.6.10、langchain-openai 1.7.1、LangGraph 1.2.15、langgraph-checkpoint-postgres 3.1.3。SDK 选择必须以锁定版本为准；下述官方文档是模式参考，具体签名仍需在编码阶段基于 lock 做验证。
- `agents/runtime.py:90-190`：一个 `create_agent` 服务入口、现含 5 个工具（含委派工具）、ModelCallLimit 6、ToolCallLimit 12、递归限制 30、输出上限 1000、sync `invoke`；Checkpoint thread 对应单个 AgentRun。
- `worker/runtime.py:150-345`：消息任务 lease、heartbeat、同会话串行、AgentRun 创建/恢复、结构化结果落库、ConversationService 幂等发布、失败码及退避。
- `application/agent_services.py:136-350`：授权的 Case/Device/事实/证据/动作/核验/任务/Skill/审核经验上下文，估算 6000 tokens 的上下文预算；`:490-540` 为固定本地 Markdown 手册按 query token overlap 的只读检索。
- `application/skills.py`：固定版本 Python Skill 目录，`diagnose-no-charge` callable，`emotion-assessment` PREPARED；加载 Skill 记录 LOADED，不等于执行完毕。
- `application/services.py:35-110` 和 `api/business.py:140-175`：progress 走 Outbox → `ConversationEvent` → SSE 历史/重连补取；有固定事件枚举和 PUBLIC/INTERNAL 隔离。进度只发 worker 开始、手册查阅开始/完成、处理完成/失败；没有模型 token delta/子 Agent 身份/任务状态/待用户输入事件。
- `persistence/models.py:513-710`：MessageJob 关联一条 AgentRun；AgentRun 的消息唯一键、状态 CHECK 未含 WAITING_CUSTOMER；ServiceTask 是 OPEN/ASSIGNED/CLOSED 的真人任务；事件有 conversation 内 sequence；业务 schema 与 checkpoint schema 分离。
- `frontend/src/features/conversation/useConversationEvents.ts` 恢复持久事件并显示固定 progress；`UIDocumentRenderer.tsx` 的选项仍走普通 `sendMessage`，UI action 当前只覆盖 `REQUEST_ASSISTANCE`。公开 UI 建立在已完成 Run 和实际公开消息上。
- Jev：活动源码、依赖、规范目录无 `Jev` 实现或 Jev 客户端配置命中。RAG：无向量库/embedding/RAG 平台；当前是只读 handbooks + 审核经验候选（最多两条且型号/关键词过滤）。SOP：`docs/service-sop.md` 是业务流程契约；Runtime 只从其中的项目资料摘取内容，不存在确定性 SOP workflow engine。
- 当前资料未证实真实 Provider 多轮、目标 OpenAI-compatible Provider 结构化/工具行为或进程中断端到端恢复：参见 `docs/phase2-validation.md`。


## 实施后基线复核（2026-10-16）

本节修正前述“实现阶段”的历史快照：A–D 代码已实现。当前执行链为 AgentRuntime `delegate_diagnostic` → AgentToolService create/resume/complete → DiagnosticAgentRuntime `ToolStrategy(DiagnosticResult)` → task/run/answer 持久化 → ConversationService `specialist.activity` Outbox → 既有 SSE/活动卡；提问通过已有 UIActionRequest 与 `DIAGNOSTIC_TASK_VIEW` 回传，最终由现有 MessageJob/Worker 继续处理。没有诊断专属业务 HTTP 路由。

锁定依赖来自 `backend/uv.lock`：LangChain 1.4.5、langchain-core 1.6.10、langchain-openai 1.7.1、LangGraph 1.2.15、langgraph-checkpoint-postgres 3.1.3。新调用只依赖当前 create_agent/ToolStrategy 与工具/运行时边界；未采用参考框架的 streaming API。专业进度通过业务 Outbox 表示真实状态，不直接暴露 LangGraph token stream。

待验/待做：真实模型结构化输出、准确性和响应延迟/成本 P50/P95；强制杀进程后的 checkpoint 恢复；后台 expires scheduler；客服专属候选来源审查 UI。现有测试不能替代以上生产验收。Jev 依用户指示暂缓。

## 官方方案与源码调研

### LangChain / LangGraph

- [LangChain multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent) 与 [create_agent 实现](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/factory.py)：官方源码显示 `create_agent` 构造模型/工具循环图，并支持 `response_format`、checkpointer 等；文档区分 subagents-as-tools、handoffs、skills、router、custom workflow。模型调用/token 增加会抬高延迟/成本；文档示例数字不是 ServiceOS 基准。
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming) 与 [subgraph implementation guidance](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/use-subgraphs.mdx)：当前文档建议 event streaming 或 `version="v2"` StreamPart；`subgraphs=True`/namespace 可标识来源。官方文档明确 per-thread 子图不支持并行调用同一 checkpoint namespace；ServiceOS 选择串行单 task，且自有 Outbox/SSE 授权，不向用户发 token stream。
- [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)：可选择 stateless、per-invocation、per-thread persistence；每个调用 fresh 的隔离适合单次咨询；需要跨轮续问的专家状态应有稳定线程与 checkpointer。文档明确同一个 per-thread 持久子图在一个节点并行多次调用存在 namespace 冲突风险；不要并行重复调用同一诊断 thread。
- [LangGraph persistence](https://langchain-ai.github.io/langgraph/concepts/durable_execution/) 与 [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)：checkpointer 是 thread/执行状态，resume 要用稳定 thread；interrupt 节点会从节点头重跑，副作用应放在 interrupt 之后或使用幂等键；中断异常不能被 bare `except` 吞掉。Checkpoint 不等于业务 task、案例事实或审计发布。
- 适用：本项目已有 LangChain `create_agent`、LangGraph PostgresSaver 和独立 worker。建议第一阶段把专家作为受限 typed tool 或父流程中的子图调用，复用 provider/checkpointer/Outbox/ConversationService。当前依赖范围兼容 LangChain 1.x `create_agent` 基础面；LangGraph 1.2.15 锁定版是否提供所用 `stream(..., version="v2", subgraphs=True)` 与同源异步细节，编码阶段要在环境对照 lock 验证，不能据“最新版文档”默认通过。

### OpenAI Agents SDK

- [Multi-agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/) / [Agent.as_tool reference](https://openai.github.io/openai-agents-python/ref/agent/)：Agents as tools 保留 manager 控制权，子 Agent 收到生成的窄输入，manager 继续综合并拥有公开回复；`on_stream` 可以在内嵌 Agent Tool 流运行时接收子 Agent stream。
- [Handoffs](https://openai.github.io/openai-agents-python/handoffs/)：把控制权交给明确的 specialist， specialist 可直接回答；handoff input schema 是路由元数据而不是替代主输入；默认转发对话历史，`input_filter` 可裁剪，但 handoff 仍在同一个 Runner turn，且 SDK 提醒不要把该过滤误认为完整脱敏。需要把控制权交回主 Agent 才要显式设计 handoff-back。
- [Running agents / streaming](https://openai.github.io/openai-agents-python/running_agents/) 和 [HITL](https://openai.github.io/openai-agents-python/human_in_the_loop/)：`Runner.run_streamed` 暴露 run item/agent 流；审批中断可序列化 `RunState`、作决定后恢复。客户端不应提交自带状态；服务端持有并鉴权 state。
- [OpenAI Agents SDK customer-service example source](https://github.com/openai/openai-agents-python/tree/main/examples/customer_service)：展示 Triage、FAQ、Seat Booking 等 Agent、transfer handoff、`current_agent` 在请求轮之间保存，及每轮交互时以 `new_items` 展示 agent/handoff/tool 身份。是 SDK 示例，没有 ServiceOS 的 tenant/Case/权限/事务/SSE 语义。
- [OpenAI Customer Service Agents Demo](https://github.com/openai/openai-cs-agents-demo)：Python Agents SDK backend + Next.js/ChatKit，用多个航空售后 Agent 展示 orchestrator 和 active specialist；展示体验和身份分层。依赖/数据/架构是演示工程，不是可移植生产方案，也没有 ServiceOS 的业务持久化/权限/恢复合同。
- 适用与局限：`Agent.as_tool + on_stream` 是最贴近产品语义的“主 Agent 始终主协调、专业 Agent 可见”的参考。但当前后端未安装 `openai-agents`，使用 LangChain + OpenAI-compatible ChatOpenAI，迁 SDK 会增加并行运行时、协议/trace/模型适配和恢复边界。只借鉴编排角色和事件，不引入此 SDK。

### AG-UI

- [AG-UI Events docs](https://docs.ag-ui.com/concepts/events)、[Subagents](https://docs.ag-ui.com/concepts/subagents)、[Interrupts](https://docs.ag-ui.com/concepts/interrupts)、[官方 1.0 schema 源码](https://github.com/ag-ui-protocol/ag-ui/blob/main/docs/spec/1.0/basic/index.mdx) 与 [LangGraph adapter 源码](https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/ag_ui_langgraph/agent.py)：事件包含 Run end outcome/interrupt、subagent lifecycle 与 invocation attribution；`subagentRunId` 是一次调用身份而不是可复用类型。项目只采纳身份分离概念；发布权限、业务持久化、用户答案仍由 ServiceOS 控制。
- [AG-UI subagent rules](https://docs.ag-ui.com/concepts/subagents)：身份归属是来源 attribution，不自动提供授权、事务或持久恢复。将原生工具调用参数/工具结果输出给用户可能暴露隐私；ServiceOS 应只用公开白名单活动标签，不透出原始工具 payload 或 reasoning 类事件。
- 适用：作为公开事件命名/身份语义参考，把子 Agent 的 `run_id` 和 stable `agent_type`/display_name 分开，事件归属写入现有 event `data`。不应迁移到完整 AG-UI event transport，当前 SSE 有兼容稳定的 seq、可见性和授权过滤。

### Support/HITL demos 与 Microsoft Agent Framework

- [OpenAI Customer Support Agent with Human in the Loop Demo](https://github.com/openai/openai-support-agent-demo)：Next.js、Responses API、File Search、客服和客户双视图、流式建议回复、客服编辑/发送、工具 action 建议/审核，普通动作可自动执行；README 明确 action 是占位函数、Demo 不生产可用。借鉴“AI 对客服建议、客服仍控制敏感外发”与流式 UI 体验，不复制 File Search/Next.js/样例身份/操作实现。
- [Microsoft Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/) / [checkpoint](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints) / [HITL](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop) / [checkpoint + HITL source sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/checkpoint/checkpoint_with_human_in_the_loop.py)：Workflow checkpoints 可持久 superstep 状态和 pending requests；HITL request/response 可暂停并在恢复时重发请求。示例依赖其 runtime/FileCheckpointStorage，部分 Foundry 示例还依赖 Azure。
- [Python checkpoint + HITL sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/orchestrations/handoff_with_tool_approval_checkpoint_resume.py)：示范 FileCheckpointStorage 下暂停、进程退出/恢复、读取 pending request 再回复。它需要 Agent Framework/Foundry 的运行时生态（部分示例需 Azure Foundry），不契合当前依赖和部署目标；用于核对 durable wait/resume 职责，不作迁移目标。

## 控制模式比较（按 ServiceOS 需求）

| 模式 | 控制权 / 用户身份 | 上下文与恢复 | 延迟/成本 | 本项目选择 |
|---|---|---|---|---|
| Tool Subagent | Service Agent 收口公开答复；专家作为专家事件显式呈现 | 传最小 DiagnosticTask DTO；独立 specialist thread/checkpoint；业务 task 在 Postgres | 一个专家模型调用 + 主 Agent 接收工具结果后可能再调用；增加 token/模型延迟；按需触发 | **默认**：最满足单入口/自主专业推理/主控结果的要求 |
| Graph Subgraph | Parent graph 统一控制，图节点边界清晰 | typed graph state；按 invocation/thread checkpoint 可选；interrupt/resume 适合后续多轮 | 多步骤确定性更强；编排开发、测试复杂度较高；subgraphs 可能增加流集成成本 | 若后续需要多分支、并行或图内 interrupt 时再评估；当前跨消息等待由 DiagnosticTask/Answer + MessageJob 处理 |
| Handoff | specialist 临时成为当前 Agent，可能直接面向用户；返回主 Agent 需要 handoff-back | 默认可能继承会话史；必须过滤上下文；对接持久业务 task 仍需独立设计 | 可能少一次 manager 综合调用；多 hop/多轮状态与 UI 身份更复杂 | 不采用：与 Service Agent 始终主协调者、统一发布入口冲突 |
| Workflow scheduler | 代码定义节点顺序、条件、等待、重试；Agent 作某些步骤 | task/workflow 持久化、业务等待和 checkpoint 协调明确 | 确定性和审计更好，设计/运营成本最高；响应回合可能更长 | SOP/授权/核验/回访走现有领域应用服务/Job；仅当诊断工作流出现真实多分支/并行/超时等待再评估 LangGraph custom workflow |

## 推荐决策

1. 先用 Service Agent 现有 `create_agent` 判断“可直接答复 / 需要专业诊断 / 需要人工 / 安全停止”，只有明确诊断证据缺口、跨手册多步推理、现有 skill 无法覆盖、或用户明确要专业排查时调用唯一 `diagnostic` 工具。安全危险征兆优先触发固定安全规则/人工升级；不要为每条消息额外调用 Router。
2. `diagnostic` 工具接收应用生成的 `DiagnosticTaskInput`，不是模型可自由传租户、设备或任意消息历史；其 context 由 `AgentContextBuilder`/专用 query service 最小化重组。专家只读 `lookup_manual`/经过审核经验和允许的 Skill 方法，不能调用 propose_action、写事实或公开消息。
3. 专家返回严格 Pydantic `DiagnosticResult`：`assessment`（hypothesis/uncertain）、`evidence_refs[]`（只允许任务上下文已有证据 ID 或手册条目来源）、`unknowns[]`、`recommended_next_step`（解释/安全/追问/转人工）、可选 `question`（结构化 question/options/allowed free text/required），`confidence_band` 为非定量粗枚举。Server validates resource refs/version/size/enum; 专家输出一律为假设，只有客服/用户或受信工具通过现有核验流程后可晋升事实。
4. 用户可见的专家活动是独立于专家内部工具 result 和最终回复的 allowlisted projection：started, safe public stage, waiting_for_customer, result_ready, failed/retryable. UI 名称明确“诊断专家”；公开意见通过 Message/UIDocument 受后端 authorization，不把 reasoning、prompt、tool args/results、内部证据或 STAFF note 透出。
5. `DiagnosticTask` 是跨 AgentRun 的领域状态（OPEN/RUNNING/WAITING_CUSTOMER/WAITING_STAFF/COMPLETED/FAILED/CANCELLED/EXPIRED；version、expected refs、attempt key、current specialist run、input/output payload 和截止时间）。AgentRun/Checkpointer 仍是执行尝试/图状态；task result 和 resume command 持久于业务库。客服改 policy/ Case 更新/用户撤回时重核并阻断过期公开答复。
6. 当前 A–D 实现选择与历史建议的差异：没有新诊断任务 API；C 复用 `DIAGNOSTIC_TASK_VIEW` + 现有 UI Action 写入答案/Message/MessageJob，随后由新 AgentRun 从业务 task/answer 重建上下文。同一 lease retry 才复用 specialist checkpoint thread。该边界不让长 LLM 占用 HTTP，也不依赖 checkpoint 作为答案权威。
7. `AI_LEAD + AI_AUTO` 可以发布专家的经过 schema 验证、来源脱敏的诊断摘要；`AI_REVIEW_REQUIRED` 只产生 INTERNAL draft/UI 给客服决定；`CO_SERVICE` 默认内部，仅显式授权可外发；`HUMAN_LEAD/HUMAN_ONLY` 永远只留内部给 staff。模式变化后的 publish 要由 ConversationService 重新读取当前 policy。未知结果只显示“未完成/需重试”，绝不伪造完成。
8. SOP workflow 负责流程阶段/资格/超时/审批/Case 状态迁移；Diagnostic Agent 对证据生成假设和安全可执行建议。Skill 是可版本化、受能力/风险过滤的方法说明；RAG 是按授权模型/知识版本/来源检索证据；Jev 当前未实现，后续若接入应作为检索 adapter/来源，不作为流程引擎或授权源。

## 已批准决策与实现后仍需验证事项

- 用户已批准按推荐值执行：`AI_REVIEW_REQUIRED` / `CO_SERVICE` 专家活动默认 INTERNAL；待以实际协作权限代码和 API/SSE 测试验证。
- 用户已批准等待客户 7 天后过期；已在授权 UI projection 和答案提交时懒标为 EXPIRED。后台到期扫描/通知策略仍未实现/无承诺。
- 已实现 `specialist.activity` 固定 schema，复用现有 event envelope；未知/无效 stage 被前端忽略，服务端 Outbox 仍是权限边界。
- 真实模型 structured output、TTFT、质量、多工具行为、成本与 P50/P95 未测；增加 subagent 会增加成本和尾延迟，必须按需触发。
- 用户明确将 Jev 搁置；当前不推断其产品身份，不新增依赖或检索 adapter。
