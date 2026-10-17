# 功能契约：客户与客服交互对齐

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 所属阶段、功能切片 | 交互与真实业务契约对齐；客户协助状态、客服任务队列、AI 回复草稿审核链、活动投影 |
| 用户目标与入口 | `/support` 会话、服务资料与历史；`/desk` 任务队列、消息时间线和服务/案例上下文 |
| 涉及对象及关系 | Conversation、ServiceTask、Message、AgentProposal 独立。新建的 StaffReplyDraft 关联 Conversation 与来源 Proposal；不把 Conversation 当 Case |
| 前端负责人 / 后端负责人 / Agent 负责人 | 同仓库协同；Agent 不新增旁路业务写入，仍经应用服务和类型化命令 |
| 集成负责人 | 本功能契约 |
| 契约状态与版本 | 2026-10-17 按用户授权的保守语义确认；实现前后以真实 OpenAPI 校验 |

## 2. 已有操作及拟新增缺口

### 已有操作（保持兼容）

- `POST /conversations/{id}/ui-actions` / `invoke_ui_action`：客户唯一人工入口；使用 `client_action_id + ui_id + revision + expected_conversation_version`，返回 `UIActionResult(ACCEPTED, task_id?, replayed)`。接受只代表持久任务已创建，不表示客服已接手。
- `GET /conversations/{id}/tasks` / `list_tasks`：STAFF 同租户读取 `TaskRead`；客户当前 403。
- `POST /tasks/{id}/claim` / `claim_task`：STAFF 以 `expected_version` 接手 OPEN task；竞态输家 409。
- `POST /conversations/{id}/messages` / `send_message`：PUBLIC/INTERNAL 持久消息，以 `client_message_id` 幂等；202 receipt 才是已接收事实。
- `GET /conversations/{id}/proposals`、`POST /proposals/{id}/decision`：动作类 proposal 可保留原审阅；REPLY 的直接 APPROVED 现在返回 409，必须先使用下述草稿链，防止批准即发布。

### 新增操作

1. `GET /conversations/{id}/customer-assistance`：CUSTOMER 仅读本人、当前 tenant、该 conversation 下由本人发起的人工任务；返回 `CustomerAssistancePage(items: CustomerAssistanceRead[])`。读模型只含 `id,status(OPEN|ASSIGNED|CLOSED),version,created_at`，不含原因、case、客服身份或队列数据。无记录为空数组。没有取消/关闭/改派语义。
2. `GET /tasks?queue=OPEN|MINE&cursor=<UUID>&limit=1..100`：STAFF tenant 范围；OPEN 是未分配 OPEN tasks，MINE 是当前登录客服 active assignment 且 status ASSIGNED。按 `(created_at,id)` FIFO 正序，cursor 独占，返回 `TaskQueuePage(items: TaskRead[], next_cursor)`。不返回全体他人已分配任务，不表示 presence。
3. `POST /proposals/{id}/reply-drafts`：STAFF 将有效内部 REPLY proposal 复制为持久的编辑草稿；原 proposal 保持 DRAFT/INTERNAL，不批准、不发布；同一 `draft_id` 重试幂等。响应 `StaffReplyDraftRead` 包含 draft id、conversation/proposal id、content、status `IN_COMPOSER|EDITED|APPROVED|SENT`、version、created_at。
4. `GET /conversations/{id}/reply-drafts`：STAFF 同租户读取会话内草稿，用于刷新恢复。
5. `PATCH /reply-drafts/{id}`：STAFF 同租户、草稿拥有者；`expected_version`、新 content；只允许 IN_COMPOSER/EDITED；更新到 EDITED 并版本递增。冲突 409。
6. `POST /reply-drafts/{id}/approval`：STAFF 同租户；`approval_id` + `expected_version`；将未发送草稿置为 APPROVED，单独记 `approved_by`，不发消息。相同 key/hash 回放原回执；冲突/终态 409。
7. `POST /reply-drafts/{id}/send`：STAFF 同租户；`client_message_id` + `expected_version`；仅 APPROVED 可以发。重新按当前 Conversation policy 检查 PUBLIC 授权，在同一事务经 ConversationService 发布 STAFF PUBLIC Message，持久化消息/outbox 并把草稿置 SENT。响应现有 `MessageReceipt`；相同 message key 回放，内容冲突 409。未知网络结果必须读草稿/消息/事件或用同一 key 对账，禁止新 key 盲重发。

新增持久模型 `StaffReplyDraft`：tenant、conversation、source proposal、creator、content、status、version、approval key/hash/actor/time、sent message、send key/hash、created/updated 时间；外键 tenant-scoped；状态 CHECK；`send_key`、审批 key 仅在各自草稿内唯一。原草稿内容和审批主体是审计字段。发送仅产生作者 STAFF 的 PUBLIC 消息；不得把原 AI 内容改标成 Agent 已发送。审批者可与编辑者相同：当前权限体系没有 maker-checker 约束，不新增猜测的分离职责。

## 3. 授权、visibility、重复与状态

- 所有读写由 FastAPI 身份和 tenant/resource authorization 执行；CUSTOMER assistance read 仅本人发起记录，proposal/draft/queue 只限 STAFF。
- 仅数据库持久化且授权为 PUBLIC 的 Message 进入客户时间线/SSE。草稿、提案、INTERNAL 消息永不进入。
- 请求人工不自动切 HUMAN_LEAD；OPEN 文案“已提交，等待客服接手”，ASSIGNED 文案“客服已接手”，不显示 ETA/等待时长/在线/正在查看。CLOSED 只在真实返回时展示。
- 同一客户、会话和 Case 已有 OPEN/ASSIGNED 协助 task 时，新的不同 action key 复用该 task，保留原原因且不产生第二条状态事件；CLOSED 后可再次创建。Conversation 行锁串行化创建；这是防止重复点击/刷新放大人工队列的保守规则。
- 请求入口继续仅用受信 UI Action。事件新增 `assistance.status_changed`：仅客户发起 Task，PUBLIC，只含 `task_id,status,version`，创建与接手状态变化在事务写入；FollowUp/内部 task 不发此事件。既有 `assistance.requested/assigned` 保持 INTERNAL。
- 队列读取是快照页，无写副作用；认领继续使用原 `claim_task` expected_version 并发语义。
- AI 内容进入 composer、编辑、审批、发送是 4 个独立状态。批准本身不向客户发布。发送时再次做当前策略/会话授权检查；不通过返回 409，草稿保持 APPROVED 供用户处理，不自动降级或重发。

## 4. 事件、异步与恢复

- 事件仍用 ConversationEvent 持久 sequence；SSE 使用 `Last-Event-ID`，补取用 `event-history?after=`。新 `assistance.status_changed` 的消费者按 task_id/version 更新客户协助查询；proposal/draft 写入后刷新对应客服查询，消息只认 `MessageReceipt` 和持久消息。
- 新增已发布回复呈现事件 `agent.reply.delta`：仅由 `ConversationService.publish_agent_response` 在后端当前 PUBLIC 协作策略授权且已保存为 PUBLIC AGENT Message 后产生。Outbox 数据仅含 `message_id`、从该规范消息正文切出的 40 字符 `text` 与从 0 开始的 `part_index`；派发再次核对同租户、会话和 PUBLIC AGENT 来源，且分片必须精确匹配已存正文。INTERNAL 草稿不产生分片，未经保存和授权的模型 token 不进入事件。实体接地诊断不拦截正常发布；主 Agent Prompt 要求不虚构型号/数值。
- 分片 Outbox 与规范消息及 `message.created` 在同一事务保存；按分片顺序先送出 `agent.reply.delta`，最后送 `message.created`。SSE 对已发布分片逐条交付并短暂让浏览器渲染；前端临时显示正文，收到 `message.created` 后查询规范消息并替换临时内容。重连按持久序号续传；完整消息快照始终可恢复。
- 这属于“发布后 SSE 分段呈现”，不是模型生成 token 流；它不缩短 Agent/模型生成或安全检查耗时。页面刷新时仍直接读取规范消息，不重播历史动画。
- event stream 只作刷新提示，不能取代 query/read 的权威快照；重复/跳号按既有 sequence 去重和补取；连接失败维持轮询和手动刷新。
- 403 表示拒绝，不自动重试；404 隐藏不存在或无权资源；409 刷新真实状态并由操作者决定下一步；网络超时显示“结果未确认”并按原 key 对账。
- 没有 presence API、assignment ETA、排队服务等级时间和人工响应 SLA，不呈现相关状态。

## 5. 客户/客服映射表

| 角色与页面 | 用户意图 | UI 状态与触发 | HTTP operationId/路径或事件类型 | 请求/响应 schema | 后端应用服务位置 | 授权与租户范围 | visibility | 幂等键/预期版本 | 异步回执和事件游标 | 失败/重试/恢复 | 测试/验收证据 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 客户 `/support` 会话入口/历史/新对话 | 创建或选择会话 | loading/empty/current/history/new | create_conversation、list_conversations、read_conversation | CreateConversation→ConversationRead/ConversationList | BusinessService 与 conversation_reads | 本人/tenant | 不涉及 | 新建目前无客户端幂等 key | HTTP 快照 | 401/403 呈现重试；不可声称创建成功 | test_business_api conversation ownership | 已有契约 |
| 客户 `/support` 消息时间线 | 查看授权消息 | PUBLIC 新消息更新、INTERNAL 隐藏 | list_messages、message.created、list_event_history、stream_events | MessagePage/EventPage | ConversationService.messages/events | CUSTOMER own conversation | 仅 PUBLIC | cursor UUID；读取无写 key | persistent sequence/Last-Event-ID | 断线按游标补取，事件仅刷新 query | visibility/SSE tests、browser/live | 已有契约 |
| 客户 `/support` 发送消息 | 发送公开消息 | draft/sending/accepted/unknown/failed | send_message、message.created | SendMessage→MessageReceipt | ConversationService.send_message/outbox | CUSTOMER own conversation | 固定 PUBLIC；客户不能写 INTERNAL | client_message_id/request hash | 202 QUEUED/NOT_SCHEDULED + event cursor | 原 key 对账，不生成新 key 自动重试 | message dedupe tests | 已有契约 |
| 客户 `/support` AI/专项诊断活动 | 看真实阶段/问题 | 只依据允许投影的真实事件及 UI document | agent.progress、specialist.activity、ui-document | EventRead/UIDocumentRead | agent/diagnostic services 与事件投影 | CUSTOMER own conversation | 仅事件公开字段 | event sequence | SSE+history | 不从文本推断完成；断线 snapshot refresh | event/SSE/diagnostic tests | 已有契约；核对公开阶段 |
| 客户 `/support` 联系人工/状态 | 发起人工协助并查看任务是否受理/接手 | 唯一按钮；ACCEPTED 后读状态；OPEN、ASSIGNED、CLOSED | `invoke_ui_action`；`GET /api/v1/conversations/{id}/customer-assistance` (`list_customer_assistance`)；`assistance.status_changed` | UIActionRequest→UIActionResult；CustomerAssistancePage | ConversationService.invoke_ui_action/customer_assistance | CUSTOMER own tenant/conversation/requested_by_customer | safe status projection; status event PUBLIC | client_action_id + expected conversation version；read-only status | ACCEPTED task id；persistent event sequence | 超时未知原 action key 对账；403拒绝；409刷新；不重建 action | UI action idempotency, owner checks, public event tests | 已实现并通过自动化验收 |
| 客户 `/support` 资料/详情、历史 Case | 查看服务与对象上下文 | real Case/Device facts/status, empty/loading | read cases/devices/device-cases, case summaries | generated CaseRead/DeviceRead | BusinessService | customer owner/tenant | authorized projection only | revision/version on mutation | existing case/device events | 403/404 distinct; stale refresh | case/device tests | 已有契约 |
| 客服 `/desk` 收件/任务与接手 | 找待接任务或本人任务 | OPEN/MINE queue, empty/loading; claim OPEN | `GET /api/v1/tasks` (`list_task_queue`)；`claim_task` POST `/api/v1/tasks/{id}/claim` | queue+cursor→TaskQueuePage; expected_version→TaskRead | ConversationService.task_queue/claim_task | STAFF same tenant; MINE active assignment only | PUBLIC/INTERNAL 不适用；仅客服队列 | claim expected_version; read cursor | assistance.assigned event internal + sequence | 409 refresh; no claim blind replay; cursor snapshot | claim race and queue tenant tests | 队列已实现并通过自动化验收；claim 沿用已有契约 |
| 客服 `/desk` 时间线/公开回复/内部消息 | 沟通或记录内部信息 | PUBLIC/INTERNAL composer; actual receipt | list_messages、send_message、message.created | MessagePage/SendMessage→MessageReceipt | ConversationService.messages/send_message | STAFF same tenant | visibility from request; customer only sees PUBLIC | client_message_id | persistent message/outbox sequence | 403拒绝、409刷新、超时对账原 key | visibility/idempotency/live tests | 已有契约 |
| 客服 `/desk` 未发布 AI 建议/回复框 | 取用 AI 草稿，编辑后审批并发送 | INTERNAL proposal→IN_COMPOSER→EDITED→APPROVED→SENT or REJECTED | `GET /api/v1/conversations/{id}/reply-drafts` (`list_reply_drafts`)；`POST /api/v1/proposals/{id}/reply-drafts` (`create_reply_draft`)；`PATCH /api/v1/reply-drafts/{id}` (`update_reply_draft`)；`POST /api/v1/reply-drafts/{id}/approval` (`approve_reply_draft`)；`POST /api/v1/reply-drafts/{id}/send` (`send_reply_draft`) | ProposalRead, StaffReplyDraftRead, versioned commands, MessageReceipt | ConversationService + typed reply-draft commands | STAFF same tenant; draft creator for edit; approval/send authorized staff | proposal/draft INTERNAL; only final persisted Message PUBLIC | draft_id; expected_version; approval_id; client_message_id | approval response no public event; send receipt then message.created sequence | 409 refetch; uncertain send reconcile by same key; never optimistic sent | new API tests + browser PUBLIC/INTERNAL tests | 已实现并通过自动化验收；旧 REPLY 直接 APPROVED 路径返回 409 |
| 客服 `/desk` 上下文/交接 | 阅读任务、案例、设备与消息上下文 | assigned identity only when TaskRead says so; linked case/device panel | read_conversation, list_tasks, list_desk_case_summaries, read_case/device | TaskRead/DeskCaseSummary/CaseRead/DeviceRead | ConversationService + BusinessService | STAFF same tenant/resource | staff context INTERNAL | expected versions for writes | events invalidate queries | conflict refresh; no inferred presence | desk summary and context tests | 已有契约 |
| 跨角色 SSE / 补取 / 缓存 | 状态变化及时可恢复 | connected/disconnected/polling/refreshing | stream_events, list_event_history + typed events | EventPage/EventRead | ConversationService event persistence/read | reauthorize each read; tenant + resource | server visibility filter | sequence cursor | Last-Event-ID and `after` | disconnected polls; duplicate sequence dedupe; no event-as-success | stream visibility/resume tests | 已有契约；新增 status event |
| 跨角色 403/409/timeout/replay | 安全恢复 | refused/conflict/unknown/reconciled | all operations above | ServiceError + operation-specific receipt | authorization/application services | same role/tenant rules | never upgrade visibility client-side | operation-specific keys/versions | authoritative DB and event cursor | 403 stop; 409 refresh; timeout reconcile exact key | backend/browser/live | 部分现有，新增写命令覆盖 |

## 6. 规则来源与权威等级

1. **A（运行证据）**：注册的 FastAPI/OpenAPI、Pydantic contract、SQLAlchemy/migration、应用服务、授权与自动化测试，决定现在实际可调用能力。
2. **B（已确认产品约束）**：四份 V1 基线、`docs/contributing.md`、本功能契约和用户确认的业务决策。规范未来设计，只有代码实现并验收后才算已上线。
3. **C（当前手册资料）**：`backend/serviceos_api/knowledge/` 中各文件明确标记的来源、产品和地域范围；只支撑其明示规则，不扩展成通用 Anker 政策。
4. **D（场景参考）**：`data/reference/hackathon/README.md` 及赛题附件；用于场景/数据参考。Published/Visible 不是现行政策，不证明真实售后系统连接。
5. **E（设计参考）**：第三方官方客服文档及截图；仅作交互原则启发，不是 ServiceOS 事实或业务权威。

规则只在来源明示范围内使用；UI 需给用户区分已核验事实、用户描述、建议和 Mock 结果。

## 7. 验收

| 路径 | 预期事实和页面表现 | 证据 |
|---|---|---|
| 客户协助成功/状态变化 | action 返回 ACCEPTED；公开投影显示 OPEN，客服认领后显示 ASSIGNED；不暴露 reason/assignee | API测试、PUBLIC event SSE、客户live |
| CUSTOMER 跨会话/STAFF/跨 tenant | 无授权拒绝；follow-up task 不出现在客户协助列表 | 403/404 API + DB tests |
| 队列分页/归属 | OPEN 仅未分配；MINE 只当前客服；FIFO cursor；跨租户隔离 | API pagination/tenant tests |
| 两名客服并发认领 | 一个成功、另一个 409；刷新队列与 TaskRead | existing race test + live |
| AI 草稿生命周期 | proposal INTERNAL；加入 composer/编辑/批准均不生成客户消息；批准后发送才生成 STAFF PUBLIC receipt | transition/idempotency/policy tests + browser/live |
| 拒绝/过期/重复 | 403拒绝，409 refresh，重复相同 key replay，内容变化冲突 | API service tests |
| 网络超时/断线 | unknown 状态对账原 id/key，history/SSE 恢复，不能假报成功 | browser/live outage-path |
| Agent 公开回复逐段显示 | 仅安全发布后的 PUBLIC Agent 正文按持久 SSE 分段显示；内部草稿/原始模型输出不显示，结束后回到规范 Message | Worker service、ConversationEvent 和浏览器分段/完成/快照回归 |
| OpenAPI/types/build | 真实 FastAPI export 与生成类型一致，browser regression | `export_openapi --check`, `npm run generate:api`, check/typecheck/build/test:browser |

## 8. 变更与落地记录

- 契约确认者与日期：用户确认按此前推荐保守语义推进；2026-10-17。
- 决策说明：人工 task 状态只展示本人发起且服务端返回的 OPEN/ASSIGNED/CLOSED；不自动切模式、不展示 SLA/presence；STAFF 队列 OPEN/MINE FIFO；草稿持久化且审批不发送，发送仅由单独命令触发并以 MessageReceipt 为准；审批人可等于编辑者；客户公开活动仅使用有 allowlist 的事件字段。
- 尚未确定而本功能不实现：取消/重派/关闭任务、SLA/ETA、online/presence、maker-checker、团队分组/跨租户队列、任务自动生成响应文本、direct assistance operation 的删除策略。
- 本次延伸实现记录（2026-10-17）：加上发布后 `agent.reply.delta` 呈现事件；不改模型生成 API、Worker 启动默认值或 OpenAPI HTTP 操作契约。真实生成前首字响应仍取决于 Agent Worker 在线状态、上下文/工具路径与 Provider 响应时间。
- 实际 operationId、path、Pydantic schema、应用服务、OpenAPI 和生成 Client 已对照真实实现；本表操作与代码一致。
- 验收结果及开发计划增量记录：见 [`docs/interaction-contract-validation.md`](../../../docs/interaction-contract-validation.md) 与 [`docs/development-plan.md`](../../../docs/development-plan.md) feature 018 条目。自动化验收已完成；生产/真实 Anker 与用户手动目视验收仍未完成。
