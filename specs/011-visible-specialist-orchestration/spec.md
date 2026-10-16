# Feature Specification: 用户可见的专业诊断 Agent 委派

**Feature Branch**: `011-visible-specialist-orchestration`
**Created**: 2026-10-16
**Status**: 阶段 A–D 功能代码已实现（2026-10-16）；真实 Provider/强制进程中断和客服 provenance review 未验收
**Input**: 设计 Service Agent 委派可见、有限权限的 Diagnostic Agent，并支持同一诊断任务中的受控用户回答及恢复。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 主 Agent 委派并收回专业结果 (Priority: P1)

客户提交问题后，Service Agent 判断现有知识/Skill 不足以完成有证据的诊断时，可向诊断专家委派一个范围清楚的任务。客户仍在一个服务会话内交流；Service Agent 收到结构化专家意见后决定如何继续或发布。

**Why this priority**: 这是增加 Specialist Agent 的最低有效价值，也确立单一入口及最终协调职责。

**Independent Test**: 在 PostgreSQL/受控模型条件下模拟委派和专家结果，检查只调用授权证据、schema 拒绝路径、重复请求幂等、主 Agent 可完成收口。

**Acceptance Scenarios**:

1. **Given** 简单问题可由现有规则、知识或 Skill 回答，**When** Service Agent 处理，**Then** 不创建诊断任务且不额外调用模型。
2. **Given** 复杂但安全且证据缺口可通过诊断排查的问题，**When** Service Agent 委派，**Then** 只传任务 DTO 和已授权上下文，产生一个可追踪专家执行尝试及结构化结果。
3. **Given** 专家引用未授权 Evidence、制造设备事实或返回 schema 无效，**When** 结果校验，**Then** 结果拒绝/降级，AgentRun 不写可信事实且主 Agent 收到安全错误状态。
4. **Given** 同一任务遇到 Worker lease 重领，**When** 恢复执行，**Then** 相同逻辑调用不重复写结果、事件或内部草稿。

### User Story 2 - 看见真实专业参与及意见 (Priority: P2)

客户或客服可从页面识别诊断专家参与、真实可公开阶段和最终诊断摘要；不看到模型原始推理或内部工具细节。

**Why this priority**: 专家身份可见是产品目标，但应建立在结构化委派与权限路径可靠之后。

**Independent Test**: 复用持久事件回放、PUBLIC/INTERNAL 授权和现有 Renderer，校验连接断开/刷新前后显示一致。

**Acceptance Scenarios**:

1. **Given** AI_LEAD + AI_AUTO，**When** 专家开始、更新阶段并结束，**Then** 客户看到实际专家标识和 allowlist 状态，最终摘要仅在 Message/UIDocument 经 Conversation Service 授权后显示。
2. **Given** HUMAN_LEAD/HUMAN_ONLY，**When** 专家工作仍被授权继续，**Then** 客户端无专家内容/活动，客服可查看 INTERNAL 结果，Agent 不公开答复。
3. **Given** SSE 断连、重复投递或事件历史分页，**When** 重连，**Then** sequence 去重且恢复最新权威任务/UI snapshot；不重启专家。

### User Story 3 - 专家受控提问与跨轮继续 (Priority: P3)

当诊断缺少关键证据时，专家可生成受限问题卡。客户提交答案后系统按 task/version 绑定到原诊断任务，并在异步 Worker 中恢复；刷新、超时、重试或模式切换均不会丢失/串用答案。

**Why this priority**: 跨消息等待需要新业务状态和权限边界，必须建立在前两阶段之上。

**Independent Test**: PostgreSQL task + answer command + worker recovery 流程，覆盖单次回答、重试、并发、冲突/失效和进程退出。

**Acceptance Scenarios**:

1. **Given** 当前诊断 Task 为 WAITING_CUSTOMER 且未过期，**When** 所属客户对当前 `question_id`/version 提交有效回答，**Then** 回答被幂等保存为业务消息/任务输入并恢复同一 `task_id` 的诊断；新 AgentRun 从业务 task/answer 重建上下文，lease retry 才复用原 specialist checkpoint thread。
2. **Given** 回答重复发送同一 idempotency key+内容，**When** API 收到第二次请求，**Then** 返回第一次 receipt 而不重复入队；相同 key 不同内容返回 409。
3. **Given** 旧问题 revision、其他客户/租户、已结束 Task 或不允许的字段，**When** 提交答案，**Then** 拒绝且不改变 task/checkpoint/Case。
4. **Given** 模型或 Worker 超时，**When** 用户刷新或重试，**Then** 数据库任务仍是权威状态并可安全恢复；Checkpointer 缺失时按已授权业务输入重建或失败可诊断。

### User Story 4 - 专业建议遵守 SOP 与协作策略 (Priority: P4)

诊断 Agent 的假设、证据引用和下一步建议进入现有确定性 SOP 与核验流程。客服可以审查来源和不确定性；只有既有业务服务能改变 Case、Device Passport、核验及发布状态。

**Why this priority**: 专业推理必须融入真实服务流程，同时防止建议被误当成设备事实、外部动作或已解决案例。

**Independent Test**: Specialist 输出在不同协作策略、安全征兆、未核验设备型号和案例核验状态下，仅产生允许的候选和建议；Case/Passport 的核验、状态转换仍由原应用服务决定。

**Acceptance Scenarios**:

1. **Given** Specialist 返回假设及 Evidence 引用，**When** SOP/应用服务处理，**Then** 只将引用现存授权证据的假设作为候选意见，不新增已核验 DeviceFact 或将 Case 标记 RESOLVED。
2. **Given** 安全停止、身份未核验、SOP/权限不允许或协作策略变化，**When** 发布或继续任务，**Then** 确定性服务阻止不安全步骤/公开内容并记录安全升级或人工审查。
3. **Given** 客服复核候选来源并经现有核验服务确认，**When** 归档事实或解决 Case，**Then** 保持既有核验规则和来源审计，不由模型输出直接变更状态。
### Edge Cases

- Case/Device/Conversation 关联或版本在专家完成前改变；公开前重新验证关联和权限。
- 客户发送普通消息而非问题卡答案；不自动猜测绑定到哪个等待 Task，Service Agent 按正常 turn 处理并决定是否恢复任务。
- 同一个 Case 有多个 Conversation 或同时存在多个诊断 Task；明确的 task/question 引用防止错配，不将 Case 与 Conversation 做 1:1 假设。
- Worker 恢复时 Lease 已失效、父 AgentRun 已完成或用户撤回；旧执行 fencing，禁止发布/写入。
- 用户答案包含恶意指令/超长文本、附件待检查或危险征兆；作为不可信输入，使用证据状态，不扩权；安全规则优先。
- HUMAN_LEAD、AI_REVIEW_REQUIRED 或 CO_SERVICE 策略变化发生在等待/运行/完成阶段；公开判定按最新策略重做。
- Specialist 失败或超过调用预算；安全 fallback/人工服务，不伪造诊断完成。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Service Agent MUST 保持统一用户入口、任务委派决策权和最终回复收口权。
- **FR-002**: Specialist MUST 只接收经应用服务构建的类型化任务和最小授权上下文；禁止自由传入其他租户或未关联对象。
- **FR-003**: Diagnostic 结果 MUST 使用版本化结构，并将证据引用、用户陈述、工具观察、诊断假设和建议步骤区分；模型输出不能直接晋升已核验设备事实或 Case 解决状态。
- **FR-004**: Specialist 工具权限 MUST 独立受限、显式列举且只读；不能直接修改 Case/Passport/Conversation、审批、公开发布或执行外部操作。
- **FR-005**: 专家公开身份、progress、question、result 只可由 allowlist 事件/UI projection 表达；不得发布 chain-of-thought、原始 tool args/results、内部备注、私密来源和密钥。
- **FR-006**: 所有公开消息/UI/事件 MUST 经 Conversation Service 按最新租户、actor、协作模式、reply_policy、关联和资源版本校验。
- **FR-007**: 跨用户消息等待 MUST 由独立 DiagnosticTask 业务状态持有，支持 question revision、答案幂等、过期、取消及恢复引用；Checkpoint 仅持执行状态。
- **FR-008**: 重要执行/回答/发布副作用 MUST 有幂等键和 lease/version fencing；相同请求重放返回原结果，不同请求冲突拒绝。
- **FR-009**: 当前 ServiceTask 继续只表示真人协作工作；DiagnosticTask、AgentRun、ServiceCase 和 Conversation 不得混为一个生命周期。
- **FR-010**: SOP 的流程状态/授权/核验由确定性应用服务持有；Specialist Agent 仅产生范围内诊断建议，不替代 SOP Rule。
- **FR-011**: 阶段 A/B 不得在 HTTP 请求内等待长 LLM；事件只反映实际状态；用户消息快速持久确认。
- **FR-012**: 关键 success/denial/lease conflict/duplicate/stale/recovery/policy-change 场景 MUST 有隔离 PostgreSQL 验收；真实 Provider 的结构化响应、时延和强制终止恢复单独报告。

### Key Entities *(include if feature involves data)*

- **DiagnosticTask**: 跨一到多轮交互的业务诊断工作单；归属一个 tenant/customer/conversation，可选 Case、设备关联版本、状态、问题 revision、deadline、幂等 key 和当前 SpecialistRun。
- **SpecialistRun**: DiagnosticTask 的一次执行尝试；身份是 invocation，不等于专家类型名；记录 lease/attempt、父 AgentRun、checkpoint thread、状态和结构化结果。
- **DiagnosticResult**: 版本化、可验证的专家结论、证据引用、不确定性、下一步、安全停止/追问/转人工建议及脱敏展示摘要。
- **DiagnosticQuestion/Answer**: 限定问题与选项、question revision、客户 action idempotency 和任务版本；答案绑定 DiagnosticAnswer 与客户 Message。
- **SpecialistEvent**: Conversation event 对 SpecialistRun 的来源归属与可见安全阶段投影；不包含模型内部 trace。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 既有流程可解决的问题在明确不需要专家的回归集上不额外调用 Specialist；触发判定在每个调用中可审计。
- **SC-002**: 每个已委派 Task 在一次正常完成时最多创建一个生效结构化诊断结果；故障重试不产生重复公开消息/任务/回答。
- **SC-003**: 通过权限矩阵验证的客户访问中，INTERNAL 专家结果、工具参数及原始推理返回数为 0。
- **SC-004**: 刷新和 SSE 断线后，通过持久事件回放或授权的 Task 查询恢复状态、专家身份、提问及结果；同一 Answer 重放不重复改变业务状态。
- **SC-005**: 所有诊断结论的设备规格/事实展示均标明其 Evidence 来源和假设状态；未经既有核验规则验证的 Specialist 输出导致已核验设备事实数为 0。
- **SC-006**: 模型调用次数、tokens、首个真实公开事件时延、全程延迟分别记录；A/B 阶段报告增加专家前后的 P50/P95，不能以合成值替代真实 Provider 测量。

## Implemented scope and remaining validation

Stage A–D code is present: delegated Diagnostic Agent and durable task/run; specialist activity via existing Outbox/SSE; controlled UI answer and same-task continuation; reviewed experience references and safety/human-review exits. There is no dedicated diagnostic HTTP route. The answer action uses the existing UI action endpoint and MessageWorker. `WAITING_CUSTOMER` expiry is enforced lazily at authorized projection/answer time (no scheduler). Customer-visible staff provenance review, real provider output/latency evaluation, and hard process-kill recovery remain unimplemented or unverified. Exact checks live in `progress.md`.

## Assumptions

- 复用当前 LangChain/LangGraph/ChatOpenAI/Async Worker/Postgres/SSE/UIDocument，不迁 OpenAI Agents SDK、Microsoft Agent Framework 或完整 AG-UI。
- 第一版只有一个 Diagnostic Agent，不做通用 Agent Registry、自由嵌套 Agent、并行专家群聊或远程微服务。
- 专家默认只读；复用本地手册、审核经验候选和已授权 Skill 方法。Jev 按用户要求搁置，不推断产品身份或接入方式。
- `AI_REVIEW_REQUIRED` 专家公开进度的可见性建议先默认 STAFF/INTERNAL；如用户确定希望客户看到“专家正在处理中”，只开放安全阶段，不展示结果直至客服审核。
- 长等待默认建议 7 天后 EXPIRED；作为待定实现参数，不改变 ServiceCase status；实际 retention/提醒另由产品确认。
- 这份 Spec、契约、研究与计划记录当前实施和剩余验收；Jev 暂缓。阶段完成仅指代码路径与列出的业务测试，不代表真实 Provider 生产验收完成。
