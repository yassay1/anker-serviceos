# 售后通 · 领域与接口契约 V1（设计定义）

> 本文描述 V1 的完整设计资源和约束；当前可调用接口以从真实路由导出的 [`contracts/openapi.json`](../contracts/openapi.json) 为准，尚未落地的阶段 4 操作见[完整 V1 接口提案](../contracts/proposed/v1/README.md)。阶段 2 的真实 Provider 验收仍待真实环境。图片证据路由已从应用导出，其大小、格式和扫描阈值仍是待确认提案；动作、核验、跟进和可信事实归档仍未实现。第一版原则：先实现可验证的行为，再将对应 OpenAPI 路由发布给前端。

## 1. 不变量

- `DevicePassport != ServiceCase != Conversation != AgentRun`。
- Case 与 Conversation 多对多关联；单个 Case 可以无已确认设备，Case 与 Device 多对多并标记 `primary`、关联角色。
- 业务事实由领域服务写入；LLM 提取的新设备事实先进入候选，含 `source`、`verified_by`、`verified_at`、`validity`。
- `collaboration_mode` 与 Case `status` 独立；`reply_policy` 在外发时强校验。
- 非客户可见内容不允许从客户端接口或 SSE 返回；每个查询按租户和资源身份授权。
- 任务批准 != 外部操作已成功；业务回执是执行结果的依据。

## 2. 数据域（提议表）

| Domain | Tables | Key fields and constraints |
|---|---|---|
| Identity | `customers`, `staff_users`, `tenant_memberships` | `tenant_id`；customer auth scope；staff role |
| Device | `device_passports`, `device_facts` | identity verification, source case, validity, revision; device facts should be retractable |
| Case | `service_cases`, `case_devices`, `case_evidence`, `case_conversations` | `status`, `version`, links; evidence source and certainty |
| Conversation | `conversations`, `messages`, `collaboration_assignments` | `mode`, `reply_policy`, `version`; public/private; message idempotence |
| Execution | `service_tasks`, `agent_threads`, `agent_runs`, `action_records`, `approval_requests` | task assignee; thread ID; run state; action key + receipt |
| Events | `outbox_events`, `conversation_events`, `follow_up_jobs` | event id/sequence/visibility; lease and retry policy |
| Interface（设计） | `ui_documents`, `ui_action_invocations` | schema/catalog version; audience; source run; context versions; immutable revision; action idempotence and receipt |

**唯一键**：`messages(tenant_id, conversation_id, client_message_id)` where nonnull；`case_devices(case_id, device_id)`；`action_records(tenant_id, idempotency_key)`；`conversation_events(conversation_id, sequence)`。

`tenant_id` 内所有受控外键查询都必须校验租户一致；不建议未经验证就假设全局 UUID 足以保证授权。

## 3. 状态机

### ServiceCase

`OPEN → IN_PROGRESS ↔ WAITING_CUSTOMER / WAITING_EXTERNAL → RESOLVED → CLOSED`，支持具备记录的 `RESOLVED/CLOSED → IN_PROGRESS` 重开。

注意：等待人工不必等于等待外部。如果有可执行的并行任务，Case 可以继续 `IN_PROGRESS`。

### Conversation

`ACTIVE / ARCHIVED` 是会话生命周期；独立 `AI_LEAD / CO_SERVICE / HUMAN_LEAD` 协作模式。

`reply_policy`: `AI_AUTO`, `AI_REVIEW_REQUIRED`, `HUMAN_ONLY`。客服独占对外发言不等于 Agent 不能运行内部工具。

### AgentRun

`QUEUED → RUNNING → COMPLETED | FAILED | CANCELLED`，`RUNNING → WAITING_APPROVAL → RUNNING`。Run 恢复和重复执行都必须能审计。

### ActionRecord

`PROPOSED → WAITING_APPROVAL → APPROVED → EXECUTING → SUCCEEDED | FAILED | UNKNOWN`（不需要审批时可直接进入 APPROVED），`UNKNOWN` 需对账后才能重试。

## 4. 人机协作权限

| Operation | AI_LEAD | CO_SERVICE | HUMAN_LEAD |
|---|---|---|---|
| Agent draft internal message | yes | yes | yes |
| Agent publish public reply | after backend check | requires explicit grant or review | no |
| Staff publish public reply | authorized staff | authorized staff | authorized staff |
| Agent internal knowledge tools | yes | yes | only authorized tasks |
| Sensitive business action | approval based on risk and role | same | same |
| Staff change mode | authorized transition + optimistic lock | same | same |

**模式切换流程**：客服执行 `POST .../mode-transitions` + `expected_version` → 验权 → 原子更新 + event → SSE 通知 → AI 流出前再次按**最新**权限校验。流式文本不能在权限确认前泄露给客户。

## 5. API 契约（计划）

本表是早期 V1 目标目录，不是已注册路由清单，其中部分示例与当前 Schema 不同（例如模式切换现在要求 `reply_policy`，内部草稿审批使用 `/proposals/{id}/decision`）。当前可调用接口以从 FastAPI 导出的 [OpenAPI](../contracts/openapi.json) 为准；未实现的操作级目标见[完整 V1 接口提案](../contracts/proposed/v1/README.md)。新增路由须由实际 Pydantic Schema 和应用服务实现后导出，并同步生成前端类型。协作步骤见[协作开发指南](contributing.md)。

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/conversations` | create conversation |
| `GET` | `/api/v1/conversations/{id}` | read conversation, mode, reply policy |
| `POST` | `/api/v1/conversations/{id}/messages` | persist a user/staff message with idempotency key |
| `GET` | `/api/v1/conversations/{id}/messages` | cursor pagination |
| `GET` | `/api/v1/conversations/{id}/events` | authenticated SSE, public/internal event filtering |
| `POST` | `/api/v1/conversations/{id}/assistance-requests` | create human task |
| `POST` | `/api/v1/conversations/{id}/mode-transitions` | switch collaboration mode, optimistic lock |
| `POST` | `/api/v1/cases` | create case independent from conversation |
| `GET` | `/api/v1/cases/{id}` | read case progress |
| `GET` | `/api/v1/cases/{id}/tasks` | related tasks |
| `GET` | `/api/v1/devices/{id}` | device passport, verified facts |
| `GET` | `/api/v1/devices/{id}/cases` | history with source |
| `POST` | `/api/v1/approvals/{id}/decisions` | reviewer decision |
| `GET` | `/api/v1/agent-runs/{id}` | run status |
| `GET` | `/api/v1/cases/{id}/follow-ups` | follow-up jobs |

**错误约定**：401 unauthenticated；403 unauthorized；404 not found / hidden resource；409 stale version；422 invalid schema；429 throttle；503 unavailable. 幂等重试相同内容返回原结果；同 Key 内容不同返回冲突。

## 6. 两个关键示例

### A. 用户发送消息

```json
{
  "client_message_id": "msg_client_uuid",
  "content": [{"type": "text", "text": "我的充电宝无法充电"}],
  "related_case_id": null
}
```

API 受理写消息、记录待运行任务和 Outbox，回复 202 的持久消息标识。模型执行和流式反馈异步进行。

### B. 客服切换模式

```json
{
  "target_mode": "CO_SERVICE",
  "expected_version": 8,
  "reason": "需要核对保修条件"
}
```

返回新版本、模式和发言策略；后端**必须**对操作者及用户当前会话权限校验。

## 7. 事件模型

```json
{
  "event_id": "uuid",
  "conversation_id": "uuid",
  "sequence": 123,
  "occurred_at": "2026-10-12T01:00:00Z",
  "type": "collaboration.mode_changed",
  "visibility": "PUBLIC",
  "data": {"mode": "CO_SERVICE", "reply_policy": "AI_REVIEW_REQUIRED"}
}
```

建议事件：`message.created`, `agent.run.started`, `agent.progress`, `agent.message.delta`, `agent.run.completed`, `collaboration.mode_changed`, `approval.requested`, `action.completed`, `case.updated`。

**重要**：`approval.requested` 等内部事件不能被客户 SSE 订阅读出；`agent.message.delta` 仅在该消息允许公开时发送，否则只推内部流或仅保留草稿。

## 8. 客服记忆与上下文

- 短期：某次 Agent Thread 的消息/中间状态，Checkpoint。
- 结构化长期：Device Passport/已核实 Device Facts，Case、客户授权的服务属性（PostgreSQL）；它们是权威业务数据，非任意的 LangGraph Store。
- 组织知识：产品手册、政策、SOP、经审核案例与版本；不可让一次未经核实的模型总结直接更新全局知识库。
- Context Builder **按权限、相关性、时间、事实状态**读取；显式标注来源；敏感信息按需脱敏；对话中的潜在事实作为候选而非直接覆盖设备档案。

## 9. 可用性与并发场景必须测试

1. Client 重复提交同一消息，只保存一份且只触发一次逻辑任务。
2. 两个真人争抢接管，只有一人基于同版本成功。
3. 真人接管后，旧 Agent Run 尚在生成，公开输出被阻断但内部任务可继续。
4. 审批拒绝，执行器不能调用受控业务 API。
5. 执行完外部请求超时，状态变为 UNKNOWN 并查询回执，不能重新扣款/重复申请。
6. 用户断开 SSE 后重新订阅，不重启 Agent Run、不丢已持久化消息。
7. 某设备历史 Case 带置信状态，不会将模型猜测升级为“设备事实”。
8. 跨用户/租户访问拒绝，内部备注不会流向公开频道。

## 10. Generative UI 领域与协议（设计，未实现）

### 10.1 对象边界

`UIDocument` 是某一时刻、某一 audience 对业务状态的可交互投影。它可以被替换、过期或停止展示，但不能反向成为业务真相；已发布 revision 按审计与保留策略留痕。至少包含：

| 字段 | 约束 |
|---|---|
| `ui_id`, `revision` | `ui_id` 稳定，revision 单调递增；已发布 revision 不原地修改 |
| `schema_version`, `catalog_version` | 服务端 Schema 与客户端组件目录版本；不兼容时降级 |
| `surface` | `SUPPORT_INLINE` / `SUPPORT_PANEL` / `DESK_PANEL`；不能让 Agent 创建任意页面或路由 |
| `audience`, `visibility` | CUSTOMER/STAFF 与 PUBLIC/INTERNAL；服务端根据资源权限生成 |
| `source_agent_run_id?` | 可追溯生成来源；固定系统投影可为空 |
| `context_ref` | Conversation/Case/Device/Task/Action 的 ID 与版本；只允许当前租户已授权关联 |
| `components` | 通过 Catalog 校验的 `UIComponentSchema[]` |
| `issued_at`, `expires_at?`, `status` | status 为 ACTIVE/SUPERSEDED/EXPIRED/INVALID；过期后动作不可提交 |
| `fallback_text` | Renderer 不支持或 Schema 失败时仍能继续服务的简洁说明 |

`UIActionInvocation` 记录一次用户或客服从组件发出的意图：`invocation_id/client_action_id`、`ui_id/revision/action_id`、actor、输入摘要/安全引用、期望业务版本、状态、错误码、关联 ServiceTask/Approval/ActionRecord、真实回执引用。它不是另一种 Tool Invocation；需要 Agent 参与时，由应用服务创建新的任务/运行。

### 10.2 UIComponentSchema

以下是逻辑结构，不代表已发布 API，也不要求数据库逐字段存储：

```json
{
  "id": "missing-evidence-1",
  "type": "QuestionForm",
  "props": {
    "title": "请补充接口信息",
    "description": "用于确认下一步排查方式",
    "submit_label": "提交信息"
  },
  "data_source": {
    "kind": "CASE_VIEW",
    "resource_id": "case_uuid",
    "resource_version": 12,
    "binding": "missing_evidence"
  },
  "actions": [
    {
      "action_id": "submit-port-evidence",
      "intent": "SUBMIT_CASE_EVIDENCE",
      "input_schema_ref": "serviceos://ui-inputs/port-evidence/v1",
      "requires_confirmation": false,
      "idempotency_scope": "PER_ACTOR_UI_ACTION",
      "expected_case_version": 12
    }
  ],
  "permissions": {
    "audience": ["CUSTOMER"],
    "display_when": ["CASE_OPEN", "ACTOR_CAN_READ_CASE"],
    "server_authorization_required": true
  },
  "children": []
}
```

字段规则：

- `type` 必须来自目标 `catalog_version` 的白名单；未知类型拒绝或渲染统一 fallback。
- `props` 按每个组件的严格 JSON Schema 校验，默认 `additionalProperties=false`；禁止脚本、事件代码、任意样式和未审查 HTML。
- `data_source` 只能引用后端定义的 View 类型与绑定键；禁止 SQL、URL、GraphQL 文本、Prompt 或客户端自由拼接查询。
- `actions` 只声明意图和输入契约，不包含 HTTP method/endpoint；后端注册表将 intent 映射到类型化应用服务命令。
- `permissions` 是服务端生成的显示/禁用提示及解释信息，不是安全令牌。即使前端显示按钮，执行时仍重新鉴权。
- `children` 只引用同一 UIDocument 中的组件 ID；限制最大组件数、嵌套深度、文本长度和动作数量，防止失控布局与资源消耗。

### 10.3 数据来源规则

| 组件数据 | 允许来源 | 展示要求 |
|---|---|---|
| Case 摘要/流程 | ServiceCase、ServiceTask、ActionRecord、真实事件投影 | 显示当前版本、等待对象；不能由模型文本推断完成状态 |
| 设备信息 | 关联 Device Passport 和 DeviceFact | VERIFIED 与候选分开；客户视图仅含有权限字段 |
| 证据/诊断 | CaseEvidence、经校验的 Jev/Diagnosis 输出 | 区分 user statement、observation、tool result、hypothesis，并附来源 |
| Skill 推荐 | Capability Resolver 的 eligible 结果、Skill 版本与失败出口 | 显示“建议/可用”，加载或选择不等于执行成功 |
| 审批/动作 | ApprovalRequest、ActionRecord、Operation Receipt | 明确待审批/执行中/成功/失败/未知；只以回执认定外部结果 |
| Agent 进度 | AgentRun 和持久化公开进度事件 | 不泄露原始推理或内部工具参数；运行完成不等于 Case 解决 |

### 10.4 Agent 与 Skill 的 UI 决策契约

Runtime 在每次可见输出前产生 `text`, `ui_proposal?` 和 `action_proposals[]` 三类相互独立的结果。`ui_proposal` 需声明 `purpose`、目标 audience、使用的 Skill/Capability 版本、依据的 Evidence/业务版本及 fallback；没有 UI 价值时应省略。

Skill 可声明 `ui_hints`（允许组件类型、输入 schema、结果展示、风险与退出条件），但这些提示必须与平台 Catalog 取交集：

- `identify-device-and-ports` → `QuestionForm` / `ChoiceGroup` / 身份证据上传；
- `acquire-visual-evidence` → `EvidenceUpload` 与拍摄要求；
- `diagnose-no-charge` → `DiagnosticSteps`、Evidence 引用与失败出口；
- `verify-resolution` → `VerificationForm`，条件来自冻结的 Resolution Contract；
- `prepare-human-handoff` → INTERNAL `HandoffSummary` 与客服任务状态。

Rule、Capability Resolver 和服务端 UI Policy 在 Agent 之后再次过滤。Skill 文本、模型置信度或 `ui_hints` 都不能启用高风险动作或覆盖人工审批。

### 10.5 动作协议与并发

客户端提交最小动作包：

```json
{
  "client_action_id": "uuid",
  "ui_id": "uuid",
  "revision": 3,
  "action_id": "submit-port-evidence",
  "input": {"port_label": "USB-C", "attachment_ids": ["file_uuid"]},
  "expected_case_version": 12,
  "expected_conversation_version": 8
}
```

服务端按 actor → tenant/resource → UI status/revision → input schema → 最新业务版本 → Rule/审批 → 幂等键顺序校验。相同 `client_action_id` 与相同内容返回原结果；相同键不同内容返回 409。旧 revision、权限变化或版本冲突返回 409，并附可安全获取最新 UI 的方式；不得让客户端自动重放不可逆动作。

客户端校验用于即时反馈和可用性，不能替代服务端校验。高风险或外部动作必须先建立 ApprovalRequest/ActionRecord，再由既有 Action Gateway 执行；UI action 自身不能声称执行成功。

### 10.6 事件与接口方向

建议持久事件：`ui.document.published`、`ui.document.superseded`、`ui.document.expired`、`ui.action.accepted`、`ui.action.rejected`、`ui.action.completed`。事件沿用 conversation sequence 和 PUBLIC/INTERNAL 过滤；payload 传 UI 引用与状态，不重复泄露完整敏感数据。

未来 API 至少需要“读取当前可见 UI 文档/修订”和“提交 UI action intent”两类能力，必须先由真实 Pydantic Schema 和应用服务实现，再注册 OpenAPI 与生成前端 Client；本文不定义返回 200 的占位路由。

### 10.7 必测场景

1. 客户无法读取或提交 INTERNAL/STAFF UI；跨租户 UI ID 返回隐藏资源语义。
2. HUMAN_LEAD 切换发生在 Schema 生成后，旧公开回复/动作在提交时被阻断。
3. Case/Conversation version 变化使旧卡失效，刷新后不重复写 Evidence 或执行动作。
4. 未知组件、错误 props、越权 data source、任意 URL/HTML/脚本、超限树全部被服务端拒绝并安全降级。
5. Skill 被禁用或证据前置条件撤销后，旧 Skill 推荐卡不能继续执行。
6. 上传失败、Renderer 不支持、SSE 断线时，固定表单/文本路径仍可完成流程。
7. 动作成功但业务核验未通过时，Case 不进入 RESOLVED；UNKNOWN 外部结果不显示成功。
8. 组件满足键盘、屏幕阅读器、错误聚焦、移动端和简体中文长文本要求。
