# V1 设计来源说明

本次主要依据是用户从聊天「项目定位与技术框架」提供到 `D:\proj\共享docs` 的五份定稿文件，见 [来源清单](baseline-provenance.json)。仓库主文档分别承担产品、架构、领域与实施计划的权威职责。

共享目录未包含架构末尾提及的原始 `docs/references.md`，因此此文件只补齐引用说明，不声称恢复了原聊天的全部调研资料。

旧 A1229 原型的资料来源与历史研究随原型归档在项目外 `D:\proj\Anker SreviceOS-archive-20261013\legacy\specs\001-device-resolution-loop\`；历史发现记录位于该归档的 `planning/findings.md`。这些只用于追溯，不属于活动工程入口，旧技术选型以 V1 主架构为准。

定稿将 Dify/Onyx 作为前后端与 Worker 组织参考，将 Chatwoot 作为会话与接管参考；阶段 0 未复制这些项目源码、未据此新增框架，也未开展 Parlant/LangGraph 对比。

## Agentic Interface / Generative UI 参考（2026-10-13 核对）

- [OpenAI：Add UI to your MCP server](https://developers.openai.com/plugins/build/chatgpt-ui)：采用“UI 只在查看、比较、编辑、确认、导航结构化信息时增强体验”“工具在无 UI 客户端仍可用”“服务端返回权威更新后再渲染”“组件状态不作业务真相”等原则。本项目不采用远程 iframe 组件方案。
- [OpenAI Plugins Reference](https://developers.openai.com/plugins/reference)：参考 `structuredContent` 与声明 `outputSchema` 匹配、模型可见数据和组件私有元数据分离、CSP/域名白名单等边界；ServiceOS V1 使用自有同源 React Renderer，不直接实现 MCP Apps。
- [Vercel AI SDK：Generative User Interfaces](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces)：参考“类型化工具调用/结果映射到已编写组件”以及输入可用、输出可用、错误等明确状态。本项目不更换 FastAPI + React 技术栈，也不引入 Next.js/RSC。
- [Microsoft Copilot Studio：Adaptive Cards](https://learn.microsoft.com/en-us/microsoft-copilot-studio/adaptive-cards-overview)：参考版本化 JSON 卡片、宿主原生渲染、表单提问/确认，以及连续卡片为每个提交动作提供唯一标识。
- [A2UI Catalogs](https://a2ui.org/concepts/catalogs/)、[Actions](https://a2ui.org/concepts/actions/) 与 [v1.0 候选协议](https://github.com/a2ui-project/a2ui/blob/main/specification/v1_0/docs/a2ui_protocol.md)：参考声明式数据、受信组件 Catalog、结构/数据/Renderer 解耦、revision/增量更新和动作上下文。A2UI 仍在演进，本项目只借鉴模式，V1 不把它设为运行时依赖或对外兼容承诺。

上述资料用于设计取舍，不证明本项目已经实现 UI Schema、Renderer 或对应接口；真实范围以 [开发实施计划](development-plan.md) 和阶段验收记录为准。

## 多人协作与接口集成参考（2026-10-13 核对）

- [FastAPI：Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)：`APIRouter` 可按业务拆分并由主应用组合；本仓库现有业务路由尚集中在一个文件，指南仅作为后续渐进拆分依据。
- [Kubernetes SIG Scheduling：Contributing](https://github.com/kubernetes/community/blob/main/sig-scheduling/CONTRIBUTING.md)：重大 API 或重构先明确设计和审阅责任；本项目使用简短契约与验收场景，不照搬 KEP 治理。
- [GitHub：贡献指南](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors)、[CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)、[受保护分支](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)：参考任务入口、审阅责任与状态检查。仓库目前未配置 CODEOWNERS 或分支保护，不能将这些参考写成现行门禁。

项目取舍与可执行步骤见[协作开发指南](contributing.md)。

## 可见专业 Agent 研究来源（2026-10-16，已批准方案与实现依据）

所有来源是官方文档或项目源码；链接只支持模式/局限结论，不表示其软件已采用。逐项代码依据、版本核对和取舍矩阵见 [011 research](../specs/011-visible-specialist-orchestration/research.md)。

- [LangChain Multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent)：Subagents / Handoffs / Skills / Router / Custom Workflow 控制模式及 tokens/model calls 取舍。选择 subagents-as-tools 保持主管 Agent 最终控制。
- [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)、[Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)、[Persistence](https://langchain-ai.github.io/langgraph/concepts/durable_execution/)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)：子图流 namespace、独立/共享 checkpoint 模式、thread 状态、interrupt 重跑/恢复及副作用安全要求。
- [OpenAI Agents SDK orchestration](https://openai.github.io/openai-agents-python/multi_agent/)、[Agent reference (`as_tool`/`on_stream`)](https://openai.github.io/openai-agents-python/ref/agent/)、[Handoffs](https://openai.github.io/openai-agents-python/handoffs/)、[HITL](https://openai.github.io/openai-agents-python/human_in_the_loop/)：manager-as-tools、handoff、子 Agent streaming 回调和持久人工审批参考。SDK 未安装，故不迁移运行时。
- [OpenAI Agents SDK customer-service example](https://github.com/openai/openai-agents-python/tree/main/examples/customer_service)：开源真实源码展示 agent identities、Triage→specialist handoff 与当前活跃 Agent 状态；只作交互设计参考。
- [OpenAI Customer Service Agents Demo](https://github.com/openai/openai-cs-agents-demo)：Agents SDK Python 后端 + Next.js/ChatKit 的多 specialist UI 演示。示例航空业务/工具并非 ServiceOS 的权限或持久化代码。
- [AG-UI Events](https://docs.ag-ui.com/concepts/events)、[AG-UI v1.0 schema](https://github.com/ag-ui-protocol/ag-ui/blob/main/docs/spec/1.0/basic/index.mdx)：`SUBAGENT_*` lifecycle、活动事件和 per-invocation `subagentRunId` attribution 参考。当前不迁移 transport；此 attribution 本身不提供 ServiceOS 权限/持久化。
- [OpenAI Customer Support Agent with Human in the Loop Demo](https://github.com/openai/openai-support-agent-demo)：双 customer/staff视图、客服编辑发布建议、敏感 action审批和流式建议；仓库明确是 Responses API demo，工具为占位，非 production-ready。
- [Microsoft Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/)、[checkpoint](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)、[HITL](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop/) 与[官方 Python checkpoint resume sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/checkpoint/checkpoint_with_resume.py)：工作流 superstep checkpoint、pending request恢复和人工交互参考。新框架及其云存储依赖不纳入推荐架构。

### 选型复核（官方文档，2026-10-16）

- [LangChain multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent) 将 subagents-as-tools（manager 保持控制权）、handoffs（切换当前控制者）、router 与 custom workflow 分开说明。ServiceOS 的统一入口与最终答复授权更适合 tool subagent。
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming) 与 [subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) 提供带 namespace 的子图事件和不同持久化模式；stream 不提供 ServiceOS 的 tenant/role 授权或 Outbox 事务，所以当前仅借鉴来源归属，不把模型 token 流公开。
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) / [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 说明 checkpoint/thread 用于执行状态与恢复。ServiceOS 的 DiagnosticTask/DiagnosticAnswer 才是跨消息业务状态与权威答案记录。
- [OpenAI Agents SDK `Agent.as_tool`](https://openai.github.io/openai-agents-python/ref/agent/) 提供 `on_stream` callback 观察嵌套 AgentTool 的事件；这是专家可见身份/真实状态的参考实现。当前依赖未安装此 SDK，不能直接复用其事件或 Runner 持久化。
- [AG-UI events](https://docs.ag-ui.com/concepts/events) 与 [subagents](https://docs.ag-ui.com/concepts/subagents) 用 parent run 和 subagent invocation identity 描述归属。该协议不是授权、幂等或业务任务持久化，因此只借用身份/生命周期概念，不迁 transport。
- [OpenAI Customer Service Agents Demo](https://github.com/openai/openai-cs-agents-demo) 和 [Support Agent HITL Demo](https://github.com/openai/openai-support-agent-demo) 是身份分层、客服审核和公开发布的体验样例；仓库未提供 ServiceOS 所需租户、Case 事实核验与业务事务语义。
- [Microsoft Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/)、[checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints) 与 [HITL](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop) 展示工作流状态、pending request checkpoint 和恢复。它验证了长时间等待应有持久业务身份；迁移需引入新运行时与 checkpoint 存储，不符合当前最小增量。

以上资料是控制模式与恢复边界参考，不代表 ServiceOS 已采用对应 SDK。源码级参考包括 [LangChain `create_agent`](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/factory.py)、[OpenAI Agents SDK `Agent.as_tool`](https://github.com/openai/openai-agents-python/blob/main/src/agents/agent.py)、[AG-UI LangGraph adapter](https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/ag_ui_langgraph/agent.py) 与 [Microsoft checkpoint/HITL sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/checkpoint/checkpoint_with_human_in_the_loop.py)。真实依赖接口以 `backend/uv.lock` 及锁定环境检查为准；未验证的 provider-specific stream 或跨进程恢复不作为兼容承诺。

### 与锁定依赖的兼容性说明

`backend/uv.lock` 锁定 LangChain 1.4.5、langchain-core 1.6.10、langchain-openai 1.7.1、LangGraph 1.2.15、langgraph-checkpoint-postgres 3.1.3。A–D 代码在锁定包上通过 `create_agent(response_format=ToolStrategy(...))`、受限工具和 PostgreSQL checkpoints/task state 实现；新增答案契约扩展的是现有 UI Action/OpenAPI，不增加 task route。已通过隔离 PostgreSQL、前端 type/API checks 与定向 browser scenarios。真实 Provider 的结构化输出、时延基线和强制进程中断仍待验收；客服专属来源审查 UI 和过期任务后台调度也未实现。OpenAI Agents SDK、Microsoft Agent Framework 与完整 AG-UI 仍未采用，AG-UI 不是当前 transport。
