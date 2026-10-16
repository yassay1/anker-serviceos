# Feature Specification: 阶段 2 Agent 结果分离与降级

**Feature Branch**: `001-agent-result-separation`  
**Created**: 2026-10-13  
**Status**: Ready  
**Input**: V1 开发计划阶段 2 剩余项；保留已验收 Worker、Context Builder 和 Conversation Service。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 安全的文本答复 (Priority: P1)

客户提交问题后，即使 Agent 同时提出界面建议，仍可收到独立文本答复；是否公开由当前协作策略决定。

**Independent Test**: 在 PostgreSQL 会话中处理消息，核对公开/内部消息及刷新后的运行记录。

**Acceptance Scenarios**:

1. **Given** AI 自动公开策略，**When** 运行返回文本和 UI 提案，**Then** 只把文本交给 Conversation Service，UI 提案不成为消息正文。
2. **Given** HUMAN_LEAD，**When** 运行结束，**Then** 文本留在内部，UI 和动作提案不对客发布。

### User Story 2 - UI 提案安全降级 (Priority: P1)

模型提供的可选 UI 提案不符合阶段 2 契约时，系统保留可用文本并记录拒绝原因；客户可继续使用文本入口。

**Independent Test**: 用非法 audience、脚本字段、超限内容和无效结构检查拒绝及文本保留。

**Acceptance Scenarios**:

1. **Given** 有效文本和非法 UI，**When** 解析结果，**Then** UI 被丢弃、文本保留，审计记录降级代码。
2. **Given** 模型只返回普通文本，**When** 解析结果，**Then** 形成无 UI 的文本结果。

### User Story 3 - 动作提案独立与可恢复 (Priority: P2)

客服后续可在内部审计中区分动作草稿、UI 提案和客户文本；重试不会重复建立草稿或公开消息。

**Independent Test**: PostgreSQL 中创建动作草稿、模拟重试和权限变化，核对唯一性、运行结果与消息。

**Acceptance Scenarios**:

1. **Given** 工具创建动作草稿，**When** 运行结束，**Then** 结果仅引用该内部草稿，不声称动作已执行。
2. **Given** 同一消息重试或租约变化，**When** Worker 恢复，**Then** 不重复公开消息、不重复动作草稿；旧租约不能写结果。

### Edge Cases

- 结构化结果缺少有效文本或模型在有界结构校验修正后仍无法返回结果：运行以稳定错误码终态失败，不对同一已完成的坏 checkpoint 做 Job 层重试。
- UI 提案包含未知字段、任意 URL/HTML/脚本、过长文本或错误 audience：丢弃提案并保留文本。
- Provider 不支持结构化输出：普通文本可用；真实兼容性待凭据验证。
- 已保存结果后 Worker 崩溃：恢复时复用已保存结果并重新检查当前公开策略。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 运行结果 MUST 分离 `text`、可选 `ui_proposal` 和 `action_proposals`，不得把 UI/动作对象拼入公开文本。
- **FR-002**: 公开文本 MUST 经 Conversation Service 根据最新协作策略再次授权，并保持 AgentRun 幂等发布。
- **FR-003**: UI 提案 MUST 通过阶段 2 的严格、有限元数据校验；无效提案 MUST 降级为文本并留下不含原始私密内容的原因码。
- **FR-004**: 动作提案 MUST 只引用已有受控工具创建的同租户、同 Run、内部草稿；不得执行外部动作或创造业务成功状态。
- **FR-005**: 结构化结果 MUST 在 AgentRun 中持久化，并受租约令牌保护；重试 MUST 复用已保存结果。
- **FR-006**: 关键成功、权限拒绝、失败与恢复场景 MUST 经 PostgreSQL 测试；真实 Provider 多轮及杀进程验收独立标注。
- **FR-007**: Agent final output MUST use a typed structured-output contract; invalid legacy checkpoint output MUST never be published, and deterministic output-format exhaustion MUST terminate the Job without replaying the same completed checkpoint.
- **FR-008**: The Agent MUST remain configurable for OpenAI-compatible model endpoints through model, base URL, API key, timeout, and optional provider request extras; provider-specific compatibility behavior MUST be scoped to the configured endpoint and MUST NOT broaden business tool permissions.

### Key Entities

- **AgentResult**: 一次运行的分离结果，含文本、可选 UI 提案、动作草稿引用和降级代码。
- **UIProposal**: 未发布的内部交互建议，不是 UIDocument 或前端可执行组件。
- **AgentProposal**: 既有内部证据/动作草稿，只有受控工具能创建。
- **AgentRun**: 分离结果和恢复状态的持久审计记录。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 所有有效文本与非法 UI 组合均仍产生文本结果，非法 UI 不进入对客消息。
- **SC-002**: 同一 AgentRun 重试只产生一条结果消息及每个逻辑动作至多一份内部草稿。
- **SC-003**: HUMAN_LEAD 下没有本切片产生的公开 Agent 消息或公开 UI。
- **SC-004**: PostgreSQL 测试、OpenAPI 漂移与前端生成类型检查通过；真实 Provider 待验项明确记录。
- **SC-005**: Deterministic malformed final output produces one terminal `agent_output_invalid` failure and no customer-visible model text.

## Assumptions

- 阶段 2 仅持久化内部 UI 提案元数据；完整 UIDocument、Catalog、Renderer 和 UI action 属阶段 3。
- 现有 `request_missing_evidence`、`propose_action` 工具仍是提案的唯一写入口。
- 无真实 Provider 凭据时，测试替身只验证本地契约和持久化，不代表 Provider 兼容性通过。
