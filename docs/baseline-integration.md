# 售后通 V1 · 现有项目合并计划

日期：2026-10-13。主来源：用户提供的 `D:\proj\共享docs` 五份 V1 文件；哈希见 [来源清单](baseline-provenance.json)。阶段 0、阶段 1 已验收；阶段 2 的 Worker/Agent 基础实现已落地，真实 Provider 验收待凭据；阶段 3 的代码与本地检查已完成，浏览器端到端路径待复验；阶段 4 已有图片、模拟动作、结果核验与回访增量，阶段 5 仍为后续工作。2026-10-13 工作区清理后，旧 A1229 原型、旧功能 spec 和旧根级 Python 工程已归档到项目外 `D:\proj\Anker SreviceOS-archive-20261013\legacy\`；本文件内旧路径只用于说明历史设计来源，不代表活动目录。

## 文档权威与保留范围

产品、技术栈、关系和 API 以 [产品定义](product-definition.md)、[系统架构](architecture.md)、[领域契约](domain-and-contracts.md) 为主；实际交付状态以 [开发计划](development-plan.md) 为准。

## 黑客松智能服务赛题资料（团队参考）

官方提供、已脱敏的赛题业务资料和完整数据文件位于 [`data/reference/hackathon/`](../data/reference/hackathon/README.md)；百炼客服搭建教程按用户要求未纳入。该资料包含赛题业务 SOP 流程图、客诉、订单、产品问答和经销商信息，可用于场景设计、静态数据回放与后续评测集构造。该资料不改变 V1 基线，也不证明相应产品能力已实现。

材料与当前领域衔接时须保持 V1 约束：客诉内容是 Case/Conversation 的输入材料，不要求一条 Conversation 对应一个 Case；邮件中的型号、序列号和故障描述属于客户陈述或候选证据，不能直接写成已核验 Device Passport 事实；订单表是静态赛题数据，不是实时订单源；退款/换货不能通过 LLM 提示词授权，也不能据此声称真实 Anker 操作成功。经销商国家精确匹配和 Seller 模糊匹配是赛题规则参考，具体归一化和歧义处理仍须明确。

现有 Excel 有 63 条客诉记录，而说明文档提到准备 40 条机器人案例加 10 条吸奶器案例；表格显式场景只有物流咨询和故障排查/产品使用，没有独立的产品咨询标签，且包含额外产品型号。产品问答的源状态和可见性标签不替代产品版本/政策校验。赛题数据补充了可用样例，但尚未形成有标注基准、可重复评测流程或完整评测指标。

旧 `specs/001-device-resolution-loop/` 已移出活动工作区，归档于项目外；当前 `specs/001`–`005` 为按 V1 新建的活动功能切片，归档旧 spec 不作为活动产品规范。`.specify/memory/constitution.md` 仍保留为工程约束。继承证据先于判断、风险保护、解决须核验、动作幂等和可审计等原则；旧 spec 的 Phase 0 停止文字、Jinja2/SQLite 产品选型、单设备 Case 和旧状态机不覆盖 V1。不得按归档中的旧任务清单机械实施。

旧 `app/`、原型测试、业务 Skill/Capability 目录与演示素材已归档到项目外；当前唯一活动产品入口为 `backend/` + `frontend/`。其中仍被 Agent Runtime 使用的两份只读手册摘要已整理到 `backend/serviceos_api/knowledge/` 并纳入 Python 包数据。后续若需复用归档原型，先重新审查并经 V1 应用服务/类型化命令接入，避免形成两套业务规则。共享原文保持原样，本地计划勾选仅反映本仓库验收。

## 历史原型与 V1 设计对照

下表的“现有实现”列记录归档前原型的结构，不描述当前 `backend/` 与 `frontend/` 的实时状态；当前实现以代码、[开发计划](development-plan.md)和阶段验收记录为准。

| 边界 | 现有实现 | V1 目标与衔接方式 |
|---|---|---|
| Device Passport | `Case.passport` 字典、固定 A1229 夹具 | 独立 Passport/Facts 存储；候选事实有来源、核验和可撤销状态；未知身份不创建假设备 |
| Case / Device | 单一 `device_id` | `case_devices` 多对多、primary 及关联角色；导入时生成关系记录，保留旧来源 |
| Case / Conversation | `Case.messages` 内嵌数组 | 独立 Conversation/Message 与 `case_conversations` 多对多；迁移不能依赖固定一对一 |
| Case 生命周期 | `NEW...VERIFIED_RESOLVED/ESCALATED` | V1 的 `OPEN...RESOLVED/CLOSED`，带记录重开；旧诊断步骤另记任务/事件，不能丢验证状态 |
| 人工服务 | 交接包、ESCALATED 终止自动流程 | ServiceTask、Assignment、Approval；AI_LEAD/CO_SERVICE/HUMAN_LEAD 与 reply_policy 独立，人工主导时 Agent 可做授权内部工作 |
| Agent 写入 | Runtime/Tool 直接改 Case、追加消息 | typed tools → Application Service → Domain；公开消息/流交给 Conversation Service 按最新权限校验 |
| Agent Loop | 自定义 Lead/Diagnosis + LangGraph + Provider Adapter | 采用定稿 `create_agent` 与 Postgres Checkpointer；保留 Provider Adapter、Jev 结构输出和诊断方法，按权限接入 |
| 执行进程 | 同步 `Runtime.advance` | 独立 Worker、持久任务租约、超时/取消、Outbox；HTTP 快速受理，不随 SSE 断线终止 |
| 存储与事件 | SQLite Case JSON、receipt、checkpoint；部分 emit 单独提交 | PostgreSQL 业务 Schema 与 checkpoint Schema 分离；业务/消息/Outbox 同事务；对账 UNKNOWN 外部结果 |
| Skill/Capability | 5 份业务方法、Resolver/Gateway、版本/哈希 | 保留并经过 schema/风险/权限校验复用，开发 Skill 和运行时 Skill 分离 |
| Agentic Interface | 静态故事板；新 Web 仅固定消息列表/输入框 | 固定页面壳 + 受控 UI Schema + React Renderer；Agent 只能选择 Catalog 组件与 action intent，后端执行时重新授权 |
| 核验与知识 | Contract 验证、待审 Evolution | 保留核验门槛；可信事实经审查归档，经验不能自动改全局 SOP |
| Web/API | 静态 HTML，`app/web` 空包 | 单一 React Web、FastAPI 分模块 API、生成 SDK；故事板保留为体验参考 |

## 状态衔接原则（阶段 1 实施前细化）

| 原型状态 | V1 表达方向 | 必须保留的信息 |
|---|---|---|
| NEW | OPEN | 原问题、来源、创建时间 |
| EVIDENCE_PENDING | WAITING_CUSTOMER 或 IN_PROGRESS | 是否真正等待用户、缺失证据及待办 |
| READY_TO_ACT / ACTION_IN_PROGRESS | IN_PROGRESS | Rule 结果、动作、审批与回执 |
| VERIFICATION_PENDING | WAITING_CUSTOMER / WAITING_EXTERNAL | Contract、反馈来源、等待对象 |
| FOLLOW_UP_PENDING | 依据等待对象映射，另存 FollowUp Job | 到期点、检查项、是否获客户同意 |
| ESCALATED | 未解决 Case + 人工任务/协作策略 | 升级原因、交接包；不映射为 RESOLVED |
| VERIFIED_RESOLVED | RESOLVED | 已核验 Contract 与 Evidence；CLOSED 另经关闭规则 |

这张表是未来转换设计，不在阶段 0 重写数据。旧终态只读与 V1 重开分别适用于原型记录和新生命周期；重开需新事件与新的核验约定，历史核验结论保持可追溯。

## 阶段 0：历史执行顺序

| ID | 文件/工作 | 验收 |
|---|---|---|
| B001 | 根 AGENTS/README + 四份主 docs | 有来源、链接可解析；未实现与已实现区分 |
| B002 | 本文与 provenance/references | 覆盖全部关键差异和复用边界，不改共享来源 |
| B003 | `backend/serviceos_api/`、pyproject、uv.lock | API 可启动；仅真实健康接口；原型不被隐式加载 |
| B004 | `contracts/openapi.json`、导出脚本 | 内容来自应用 schema；check 模式发现漂移 |
| B005 | `frontend/` React/TS/Vite、Router、Query | /support、/desk 可访问；健康状态来自真实 API；失败可重试 |
| B006 | 生成 schema + openapi-fetch Client | 路径/请求/返回同源；类型检查与生成一致性通过 |
| B007 | npm lock、Python/Node 支持版本、CI | 干净依赖安装、测试、生成比较、构建通过；远端 CI 状态另行报告 |
| B008 | 回归、浏览器验证、计划更新 | 原型测试通过；代码与来源保持可核查；阶段 1–5 保持待实现 |

## 阶段 1：业务底座（已完成本地验收）

按如下依赖执行：

1. **D101 模型与迁移**：`backend/serviceos_api/` 建立 SQLAlchemy/Alembic，独立 DevicePassport、DeviceFact、ServiceCase、Conversation、Message 与关联表。完成条件：PostgreSQL 迁移可升级/降级；Case 可无设备；关系支持多对多。
2. **D102 身份与资源权限**（依赖 D101）：客户、客服、租户资源校验；受限本地账号适配器显式启用。完成条件：跨用户/租户拒绝，内部消息无法从客户接口读出。
3. **D103 应用服务与命令**（依赖 D102）：Case/Device/Conversation 服务、版本锁、事实候选与核验入口。参考旧 commands/rules/verification，保留纯领域验证。完成条件：模型提取不直接成为可信设备事实、旧状态不会绕过新服务。
4. **D104 Conversation API**（依赖 D103）：消息幂等、分页、Case 关联；消息+任务+Outbox 同事务。完成条件：同 key 相同内容复用，不同内容冲突；受理不等待模型。
5. **D105 用户界面**（依赖 D104）：真实发送、服务器回执、断线/失败状态；重导出契约及 SDK。完成条件：从页面写入真实数据库，刷新可恢复；不提前模拟 Agent 回答。

阶段 1 验收当时尚无 Agent、SSE、审批等端点；这些能力的后续实现见阶段 2–3。阶段 1 已验收迁移、无设备 Case、多对多关系、幂等冲突、资源隔离、事实候选/核验和消息授权；详细命令与范围见 [阶段 1 验收记录](phase1-validation.md)。

## 阶段 2：受控 Agent 闭环

依赖 D105。当前实现位置：`backend/serviceos_api/worker/` 的 PostgreSQL 任务 lease/heartbeat/retry/Outbox；`backend/serviceos_api/agents/` 的 LangChain `create_agent` 与显式 PostgreSQL Checkpointer；`application/agent_services.py` 的授权 Context Builder 与受限 proposal/manual 服务；`ConversationService.publish_agent_response` 的最新模式/回复策略复核。旧 SQLite/Replay 原型已归档，不作为新运行时；活动 Runtime 的本地只读手册位于 `backend/serviceos_api/knowledge/`。

当前保护：Checkpointer 使用 `serviceos_checkpoint` 独立 schema；API 不自动建表或启动 Worker；模型目的地、模型名及 API Key 必须显式配置；无凭据时 Worker 在领取任务前拒绝启动。工具写入只形成内部草稿，公开消息通过 ConversationService 幂等落库；`HUMAN_LEAD`、`HUMAN_ONLY` 和需人工审阅策略不会公开 Agent 输出。阶段 2 验收记录见 [phase2-validation.md](phase2-validation.md)。

阶段 2 增量已在独立 [Agent 结果分离切片](../specs/001-agent-result-separation/spec.md)中补齐内部结构化结果、受限 UI 提案降级和动作草稿引用；未发布 UIDocument 或 UI action。尚未完成的阶段 2 验收：真实模型多轮售后服务、所选 Provider 的结构化工具兼容性、进程被强制终止后的端到端恢复演示。阶段 3 已实现持久事件与 SSE 补取；真实 Provider 与进程级强制终止恢复仍待阶段 2 的真实环境验收。

2026-10-15 经验沉淀增量见 [经验沉淀验收记录](experience-learning-validation.md) 与 [功能契约](../specs/009-experience-learning/contracts/feature-contract.md)：只沉淀已核验解决 Case 的空白候选，经人工审核后作为受限参考检索；不自动改变可信事实、Skill 或 SOP。

## 阶段 3：人机共同服务

依赖阶段 2。已建立客服任务、分配、模式切换、草稿审批、公开/内部事件隔离。当前 handoff 字段用于初始任务上下文，保留来源与脱敏信息。只读 UI 文档/Renderer 和低风险 action intent 已接入对应应用服务与授权规则。

完成条件已在本地 PostgreSQL 回归中覆盖：AI → CO_SERVICE → HUMAN_LEAD 的模式与发言策略校验、两名客服同版本接管仅一人成功、旧 Agent 在接管后不能公开外发但授权内部任务可继续、公开/内部事件隔离与 SSE 补取、旧 UI revision/越权数据源/未知组件拒绝或降级。浏览器自动化因本地开发登录状态请求持续停在加载态，未将其记为通过；详见 [阶段 3 验收记录](phase3-validation.md)。

## 阶段 4：完整业务纵切面

依赖阶段 3。提供受控图片输入、明确 Mock Adapter、动作批准/执行/回执/UNKNOWN 对账、核验结果、经同意的 Follow-up 与可信 Device Facts 归档。2026-10-14 已落地图片证据后端切片：真实上传、待检查状态、本地结构检查和授权下载。图片限制仍待产品确认；多模态理解尚未实现；图片上传界面、开发环境 Mock 动作、客户结果核验、经同意的回访到期任务与 Case 来源的可信 Device Facts 归档已落地。阶段 2 真实 Provider 验收保持待验。

复用 A1229 正常/复杂/风险演示作为回归场景，而非硬编码全产品默认。完成条件：成功、失败、拒绝、未知外部结果均可审计；无重复动作；Contract 验证通过才解决。

## 阶段 5：交付与部署

依赖阶段 4。Docker/Compose 本地集成、性能 P50/P95、日志脱敏、演示重置。AWS 部署是单独有授权的任务，当前不创建资源。

CI 使用同源契约和关键业务回归。旧原型目录已完成项目外归档，不再是待迁移的活动工程；重新设计旧 spec 或从归档选择性复用模块时，须另建明确任务并通过 V1 边界审查。

## 用户表达理解与回应 Skill 增量（基础实现完成，效果待评测）

`agents/runtime.py` 已加入短的常驻规则，并按 `application/skills.py` 中少量明确中文短语，在 system prompt 临时附加详细回应指导。该短语门控是启发式，不是分类器或经售后数据验证的模型；结构化 `emotion-assessment` 仍为 `PREPARED`，没有进入可调用 Skill 列表。指导只改变当前回复的措辞与解释顺序，不持久化情绪标签，也不经模型工具调用写入 Checkpoint。它不改变业务事实、工具权限、审批条件、协作模式、Case/Device 状态、公开发布校验或持久化契约。实现范围、限制和评测门槛见[设计计划](emotion-understanding-response-skill.md)。真实模型和中文售后人工评测仍待完成。

## Generative UI 增量清单

| ID | 依赖 | 工作 | 验收 |
|---|---|---|---|
| G001 | 阶段 2 Context Builder | `UIDocument`、组件 Catalog、UI Schema/Policy Validator 与 fallback 契约 | 已实现并通过未知组件、越权数据源、任意代码/URL 拒绝及文本降级测试 |
| G002 | G001、持久事件 | UI revision/snapshot、PUBLIC/INTERNAL 事件与断线恢复 | 已实现；刷新可恢复，客户读不到 INTERNAL，旧 revision 不可操作 |
| G003 | G001–G002 | React Renderer 与用户侧问题/证据/风险/核验只读或低风险卡 | 已实现 Renderer、错误/不支持组件文本或固定表单降级；浏览器端到端仍受本地登录加载问题限制 |
| G004 | 阶段 3 应用服务 | 客服摘要/Skill/草稿/审批/流程卡和 action intent | 已实现；HUMAN_LEAD/CO_SERVICE 下不偷发，按钮提交再次鉴权、锁版本、幂等 |
| G005 | 阶段 4 Action/Verification | 回执、UNKNOWN 对账、核验与纵切面评测 | 动作完成不等于解决；只有真实回执和验证条件可更新状态 |

## 本轮验证记录

B001–B008 已完成阶段 0 本地验收；D101–D105 已完成阶段 1 本地验收；阶段 2 基础实现及离线数据库验收完成，分别见 [阶段 0](baseline-validation.md)、[阶段 1](phase1-validation.md) 与 [阶段 2](phase2-validation.md) 验收记录。真实 Provider 验收仍待配置；阶段 3 已完成本地 PostgreSQL、迁移、契约、前端构建和应用服务回归，[浏览器端到端操作仍待复验](phase3-validation.md)；阶段 4 已交付图片、Mock 动作、结果核验、回访与 Case 来源设备事实归档增量，阶段 5 未实施。2026-10-13 清理将旧原型和旧 spec 归档至项目外，不影响上述历史验收事实；共享源文件未迁移或修改。
