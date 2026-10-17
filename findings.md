# 调研发现：诊断专家独立作者消息

## 需求
- 将当前只显示为专家活动卡的诊断结果，作为一条有持久专家作者归属的会话消息呈现。
- 消息必须由后端在 Conversation Service 授权后发布；专家 runtime 不能直写业务库或绕过对话服务。
- 专家消息从验证后的结构化结果构造；不公开 `staff_summary`、原始推理、工具细节、内部备注或模型 trace。
- 复用 PUBLIC/INTERNAL、消息历史、Outbox/SSE 以及现有租户隔离；普通消息写接口不得接受可伪造作者身份的字段。

## 规范基线
- 根 `AGENTS.md`：Message 与 Case/Device/Conversation 独立；公开发布须后端授权；工具只能通过应用服务改变状态；重要写入须可幂等；保持真实进度；跨模块接口修改须读 contributing。
- `docs/domain-and-contracts.md` 的“可见 Specialist 协作扩展”目前明确：专家 attribution 不授予 Message author 身份；专家结果不自动形成公开消息；活动事件不是聊天消息。此需求是新增能力，必须同步更新该段和 feature contract。
- `specs/011-visible-specialist-orchestration/contracts/feature-contract.md` 记录阶段 A-D 已实现，`specialist.activity` 明确不是 Message，最终消息目前是 Service Agent 输出。建议将新能力作为单独增量 spec/feature contract，不回写成 011 原先已具备的能力。
- `docs/development-plan.md` 的阶段 1-5 主勾选不直接涵盖此增量；其“可见 Diagnostic Agent 委派”表 A-D 均标已实现。新功能应在该增量下另加待确认计划行/验收记录，不改写 V1 阶段勾选。
- `docs/baseline-integration.md` 确认 ConversationService 是消息发布控制点，复用 PostgreSQL lease、Outbox、消息权限边界。
- `docs/contributing.md` 要求先共同确认 feature contract，再后端实现/导出 OpenAPI，前端生成 Client 并联调；不要加空壳 API。

## 当前实现证据
- `backend/serviceos_api/persistence/models.py`：`Message` 有 CUSTOMER/STAFF/AGENT/SYSTEM 作者身份约束、PUBLIC/INTERNAL、tenant FK、`client_message_id` + `request_hash` 幂等字段；没有 SPECIALIST 或 SpecialistRun 来源。
- `backend/serviceos_api/application/contracts.py`：`SendMessage` 只有内容、Case、幂等信息和可见性；`MessageRead.author_kind` 是通用 string，未暴露作者显示名或专家来源。
- `backend/serviceos_api/api/business.py`：写消息路由接收 SendMessage，读消息使用 MessagePage；无需新增专属诊断路由即可通过真实 Message API 暴露作者类型。
- `ConversationService.messages`：按 tenant/conversation 查询，客户读取强制 `visibility=PUBLIC`，客服读取授权会话消息。
- `ConversationService.publish_agent_response`：锁会话和 AgentRun，检查 ACTIVE/lease/Case 关联；安全覆盖、PUBLICATION_GUARD 与当前 `AI_LEAD + AI_AUTO` 决定公开或 INTERNAL；写 Message、Outbox 与 AgentRun 完成同一事务。该函数写死 AGENT 作者，因此不适合伪装专家身份，应新增受控专家结果发布方法并共享/复用策略门控。
- `AgentToolService.complete_diagnostic`：验证父 lease、task/run、当前 Case/Device/Evidence/experience，再通过 `validate_diagnostic_result` 绑定 task 和允许的 evidence refs；持久化结构化结果和 SpecialistRun 状态，写 RESULT_READY/WAITING_* 活动事件后提交。当前 `validate_diagnostic_result` 不做全面公开内容审查。
- `application/agent_services.py::_public_diagnostic_summary` 对 assessment 作带假设提示的限长/联系方式兜底摘要；比直接公开 assessment + next_step 更保守，是最小安全投影的现成基础。
- `SpecialistRun` 已有 `(tenant_id,id)` 唯一键；迁移 0015 已创建该表。当前最新 migration 是 0018，新增 DB 约束按 0019 顺序接续。
- `frontend/src/features/conversation/MessageThread.tsx` 目前只识别 CUSTOMER/STAFF/AGENT，其他作者都显示“服务助手”；所有 AGENT 才启用 RichMessage/快捷回复。SPECIALIST 应有独立头像/名称/AI 假设标签，并保持非 AGENT 内容路径。
- `ConversationService.dispatch_outbox_event` 对 `message.created` 已允许 PUBLIC 投递；消息 SSE 根据 ID 让前端刷新历史。现有历史加载、分页、断线刷新无需另加 SSE 事件类型。

## 重要交互问题
- `delegate_diagnostic` 返回结果给 Service Agent，主 Agent 随后仍会生成并经 Worker 发布一条 AGENT 回复。若额外发布专家消息，需明确是否保留主 Agent 回复；建议保留协调者但约束其不复述专家 assessment，测试不重复输出。若用户希望单条消息，则需另改 Worker 完成语义/AgentRun 状态。
- `ASK_CUSTOMER` 已经通过诊断问题卡请求用户补充信息；专家消息不应复制提问。`SAFETY_STOP` 和 `HUMAN_REVIEW` 当前会被主 Agent 发布路径改写成固定安全/人工回复；专家正文应不外发。仅已完成且不需要追问/人工安全处置的结果进入候选公开路径。
- 当前建议仅在 `ACTIVE + AI_LEAD + AI_AUTO` 且 publication guard 通过时创建 PUBLIC 专家消息。CO_SERVICE / HUMAN_LEAD / AI_REVIEW_REQUIRED 下创建 INTERNAL SPECIALIST 消息供客服查看，不自动公开；这符合 feature 011 对客服 STAFF-only 默认可见的契约。
- 不把 INTERNAL SPECIALIST 消息伪装成 AgentProposal/待审批草稿，因为现有 proposal 审核只接受 AGENT 内部草稿。若未来要将专家消息纳入显式审批，另行扩展审批契约。
- `ASK_CUSTOMER` 已由诊断问题卡提问，不另发结果消息；`SAFETY_STOP`/`HUMAN_REVIEW` 不公开专家自由文本，由现有固定安全/人工回复与内部活动承担。

## 拟议契约 / 实施边界
- Persistence: `Message.author_kind='SPECIALIST'`; nullable tenant-scoped `specialist_run_id`; CHECK 约束要求 SPECIALIST 必须有关联 run、其他类型不得关联 run、客户/员工 actor ids 为空；(tenant_id,specialist_run_id) 唯一以保证每次 invocation 最多一条消息。migration 0019 并有 downgrade。
- Application/API: `MessageRead` 增加可读的作者身份/固定显示信息；可以暴露 `SPECIALIST` kind，但不必将 SpecialistRun UUID 暴露给客户。SendMessage 不增加 author-kind/display-name/run-id 输入字段。`MessageRead` 建议为 `Literal` author kind，若兼容难则只做可枚举约束与类型生成检查。
- Publish: 新增 `ConversationService.publish_specialist_result`；验证 ACTIVE 会话、当前模式和回复策略、已完成的 SpecialistRun 与所属 DiagnosticTask/父 AgentRun lease、已验证 task 结果及安全 eligibility；公开正文是服务端 allowlisted projection（明确标记“AI 假设，待核验”），不含 staff_summary/推理/内部来源内容；每 run 幂等。Message 与 message.created Outbox 和诊断完成状态必须一个事务提交。
- Frontend: 真实历史/消息事件复用现有流；SPECIALIST 显示固定“诊断专家”和“AI 假设（待核验）”，不展示内部 run 源 ID，不启用 Agent 快捷回复。
- Contract/docs: 新增 feature spec/contract，更新 011 feature contract状态/关系说明、domain-and-contracts 与 development-plan 增量记录；实现完成后记录文件/命令/结果/未验证风险。

## 技术决策
| 决策 | 理由 |
|---|---|
| 新功能按独立增量契约记录 | feature 011 已明确“活动事件不是聊天 Message”，保留历史准确性 |
| 复用消息 GET、SSE、Outbox，不加专家独立发送 API | Message 是共享会话历史；写入只能由 Conversation Service 受控完成 |
| SpecialistRun 是内部来源 FK，客户端不提供作者值 | 持久审计/幂等与防伪造；前端作者身份来自服务端读取契约 |
| 保守使用当前活动摘要投影，先不公开 next_step 自由文本 | 结构 schema 验证不等于安全审查；已有 `_public_diagnostic_summary` 限制更可靠 |
| `AI_LEAD + AI_AUTO` 可发 PUBLIC；其他有效模式只发 INTERNAL 给客服 | 与 011 专家结果客服可见、公开发言授权及 PUBLIC/INTERNAL 约束一致 |
| 同步提交诊断结果、专家消息及 Outbox | 避免有结果无消息或有消息无结果，重试保持幂等 |

## 资源
- `README.md`, `docs/product-definition.md`, `docs/architecture.md`, `docs/domain-and-contracts.md`, `docs/development-plan.md`, `docs/baseline-integration.md`, `docs/contributing.md`
- `backend/README.md`, `frontend/README.md`
- `backend/serviceos_api/persistence/models.py`, `application/contracts.py`, `application/services.py`, `application/agent_services.py`, `application/diagnostic_contracts.py`, `api/business.py`, `worker/runtime.py`, `agents/runtime.py`
- `backend/migrations/versions/0015_diagnostic_tasks.py`–`0018_loop_guard.py`
- `frontend/src/features/conversation/MessageThread.tsx`, `frontend/src/api/schema.d.ts`
- `specs/011-visible-specialist-orchestration/{spec.md,plan.md,tasks.md,contracts/feature-contract.md}`
