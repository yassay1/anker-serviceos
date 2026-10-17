# 外部资料、实现分类与阶段二计划

## C. 官方客服产品资料与适用原则

第三方资料只作为模式参考，不构成本项目实现证据。

| 来源 | 官方资料观察 | 适用原则 | 本项目边界 |
|---|---|---|---|
| Chatwoot 私密备注 | Private Note 仅团队可见；与 Reply 分开并用黄色样式避免误发。[官方指南](https://app.chatwoot.com/hc/user-guide/articles/1677235281-lesson-3-a-mastering-core-features) | PUBLIC/INTERNAL 明确切换、样式与服务端 visibility 过滤 | 不复制其 mentions/通知 |
| Intercom 团队备注 | Reply 与 Note 草稿独立保存，切换不清除另一草稿。[官方指南](https://www.intercom.com/help/en/articles/6525765-loop-teammates-or-teams-into-conversations) | 回复和内部备注分开保留，切换不丢草稿 | 本项目草稿目前只是组件状态，是否持久化需决策 |
| Intercom Inbox AI | 显示 AI 草稿；补充信息后可形成新草稿并批准；接管后保留上下文。[官方指南](https://www.intercom.com/help/en/articles/6955446-ai-features-available-in-the-inbox) | AI 建议、补充事实、新草稿、批准、公开回执分状态；交接保留已有授权 Case/Device/Task | 不复制 Fin 倒计时、自动发送或指派策略 |
| Zendesk Auto assist | AI 给客服建议，客服审核批准后才能发给客户。[官方指南](https://support.zendesk.com/hc/en-us/articles/9945148867866-About-auto-assist) | 客户不可见的待审建议，发布由服务端授权，成功以回执为准 | 不代表连接 Zendesk 或其外部系统 |
| Zendesk Draft Mode | 公开回复先以草稿编辑，提交时再次确认。[官方指南](https://support.zendesk.com/hc/en-us/articles/5627101293722-Writing-drafts-of-public-replies-in-tickets?page=1&per_page=30) | 放入回复框、编辑、批准、发送分别表达状态 | 不替用户决定 ServiceOS 的审批主体或持久化 |
| Chatwoot 队列与客服状态 | 区分 Mine/Unassigned/All、Open/Pending 等队列状态和 Online/Busy/Offline 在线状态。[官方指南](https://www.chatwoot.com/hc/user-guide/en/categories/chatwoot-101) | 会话状态、任务状态、责任人、在线状态必须来自不同真实字段 | 当前没有 presence、ETA、等待时长或跨会话任务队列 |

## D. 第一阶段调研时的能力分类（实施前快照）

以下为确认前快照；客户任务状态、跨会话客服队列和持久回复草稿三项已在用户确认后按 feature 018 契约实施。当前状态以本目录的 [`specs/018-interaction-contract-alignment/contracts/feature-contract.md`](../../specs/018-interaction-contract-alignment/contracts/feature-contract.md) 与验收记录为准。

### 已有真实能力
- 按身份/tenant 读取和创建会话、分页读取消息、收发持久消息、切换历史。
- 服务端 PUBLIC/INTERNAL 隔离；客户不能读写 INTERNAL，客服限同租户资源。
- Outbox、持久事件、SSE sequence/Last-Event-ID、event-history 补取、缓存刷新和轮询。
- 单一 customer trusted UI action 联系人工；action id+hash 幂等，返回 ACCEPTED/replayed，未知结果保留原请求。
- 客服按单会话查 TaskRead 并接手 OPEN task；版本冲突 409；协作模式有权限约束。
- 内部 AI draft Message/Proposal 已保存；当前批准操作会在后端重新鉴权后直接生成 PUBLIC AI Message 和事件。
- 专项诊断 Task/SpecialistRun、实际活动事件、类型化回答；Case、Device Passport 与 Conversation 分开建模，客户资料/案例页面接真实接口。
- 前端 schema.d.ts 来自真实 contracts/openapi.json。

### 确有缺口，先写功能契约
1. 客户任务状态：UIActionResult 只有 ACCEPTED/task_id/replayed；TaskRead 与分配事件仅内部可读。确定客户可见状态/字段、事件、取消/完成和重复请求语义。
2. 客服跨会话任务队列：打开会话后才读该会话任务；没有全局待接/我的任务查询、分页、排序或筛选 API。确定队列范围、cursor、排序和认领规则。
3. AI 草稿操作链：现有 approve 会直接公开原始 AI 草稿；无“放入回复框→编辑→独立审批→发送”状态链。确定本地/持久草稿、消息作者、审批是审阅记录还是发布、编辑/重审/取消、幂等和版本。仅复制到前端 composer 可能复用 MessageRead；若审批须与发布分离则要新增应用服务类型化命令及路由。
4. 客户活动展示：真实公开 agent.progress/specialist.activity 可补取，但专家状态 UI 目前只在 desk 渲染。确定可公开阶段和摘要后可复用真实事件；若 payload 不足再设计接口。
5. request_assistance 真实路由能创建 task 但无幂等键；当前客户前端使用有幂等的 UI action。决定该 operation 保留、限制还是整合到同一应用服务命令。
6. proposed/v1 的 case tasks 与 Agent run status 仍是 planned，不得当活动 API。

### 设计稿不得暗示
- 在线客服、正在查看、排队人数/时长/ETA；无 presence/队列数据。
- 客户点联系人工即代表已接手；Agent COMPLETED 即 Case 已解决。
- AI 或专家原始输出、内部事件、内部备注进入客户 timeline；假设当作设备已核实事实。
- AI 草稿/提案/内部备注是已发送；放入回复框等于批准；未持久 PUBLIC Message 先显示发送成功。
- 请求超时即未执行；刷新产生新 id 重发；409 自动重放。
- Conversation=Case，Passport=当前问题；Mock 回执=真实 Anker 操作。
- Hackathon Published/Visible=现行政策或真实订单接口。

## E. 第一阶段拟定的第二阶段依赖排序（历史计划，已执行）

### P0 确认业务选择
决定客户可见 TaskRead 状态与字段、一个会话允许多少 OPEN task、请求人工是否切 HUMAN_LEAD/HUMAN_ONLY、任务取消/改派/关闭、客服队列范围/筛选/排序、AI 草稿是否本地或持久、发件人身份、批准是否独立于发送、可公开的活动阶段、direct assistance operation 处理。没有经授权任务/时限数据不得显示 ETA/presence。

### P1 契约先行
按 docs/contributing.md 建新 feature contract，逐场景写 request/response/state/error/auth/tenant/visibility/idempotency/version/receipt/event/history/cache recovery/test；标出现有 operationId 复用和实际缺口，不引用 planned API。活动矩阵在用户确认后按真实决策维护。

### P2 后端（仅缺口）
可能涉及 backend/serviceos_api/application/contracts.py、application/services.py、api/business.py 或新模块并注册 main.py。只有决定持久状态才动 persistence/models.py 和 migration。业务验证复用 ConversationService/应用服务类型化命令，不复制规则。测试成功、403/404、跨租户、409、同 key 重放、冲突、PUBLIC/INTERNAL 过滤及未知失败恢复。

### P3 真实契约
后端实现并测试后，从 FastAPI 导出 contracts/openapi.json；再生成 frontend/src/api/schema.d.ts。预计影响 contracts/openapi.json、frontend/src/api/schema.d.ts、frontend/src/api/client.ts。禁止手改生成 Client 类型。

### P4 手机优先前端接入
客户保留唯一人工入口；只显示获批准的公开 TaskRead/事件；客服用实际队列 query，PUBLIC/INTERNAL 草稿独立；AI 复制、编辑、审批和发送分别表现。页面涵盖 loading/empty/in-progress/success/refused/failed/unknown，403明确拒绝，409刷新，超时以原 key 恢复。预计模块：frontend/src/features/collaboration/CollaborationPanel.tsx、conversation/StaffConversationContext.tsx、ConversationWorkspace.tsx、MessageComposer.tsx、MessageThread.tsx、useConversationEvents.ts、ConversationContext.tsx、UIDocumentRenderer.tsx、styles/workspace.css、staff.css、surfaces.css。

### P5 第二阶段验收命令（本阶段未执行）
根目录：设置隔离测试库 SERVICEOS_TEST_DATABASE_URL 后运行
- uv run --project backend --locked pytest backend/tests --require-postgres
- uv run --project backend --locked python -m serviceos_api.export_openapi --check
frontend 目录：API 变更后 npm run generate:api，然后运行 npm run check:api、npm run typecheck、npm run build、npm run test:browser。
真实本地 API/数据库浏览器运行 npm run test:live，仅用隔离本地测试库，不连生产和 Anker。
验收路径：人工请求及原 key 重试、PUBLIC timeline 排除 INTERNAL、事件断线补取、客服队列与并发 claim 409、草稿各状态及发送回执、消息/备注隔离、案例设备上下文、跨租户 403/过期 409、缓存恢复、手机及无障碍。

## 未决业务问题
1. 客户可以看到哪几个任务状态？是否隐藏 assignee？可撤回吗？可重复建多个 task 吗？
2. 请求人工是否自动切模式？
3. 客服队列是租户级还是团队级？分页、排序和权限如何定？
4. AI 草稿存浏览器还是服务端？审批仅记审还是会发布？发送作者是 STAFF 还是 AGENT？审批人要独立于编辑者吗？
5. 哪些 agent.progress/specialist.activity 阶段可公开？Summary 是否经过公开核准？
6. 无幂等 direct assistance operation 保留、限制或整合？

## 第一阶段完成声明
第一阶段仅在本独立 .planning 目录新增调研和计划；当时未改产品代码、真实契约、活动设计文档或 development-plan 完成状态，也未运行测试/导出/构建。用户随后确认按推荐语义推进；第二阶段现已完成本地实现和自动化验收，具体状态、实测命令与未完成项见 [`docs/interaction-contract-validation.md`](../../docs/interaction-contract-validation.md)。
