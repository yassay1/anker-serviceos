# Case 经验沉淀与复用 · 功能契约

状态：已实现；实际路由与字段以 `contracts/openapi.json` 和后端应用服务为准。

## 目标
从正式核验解决的售后 Case 创建待整理经验候选；授权客服撰写并由主管审核；仅将同租户已批准、适用于已核验设备型号且与当前问题相关的候选作为内部参考提供给 Agent。

## 数据与权限
- `ExperienceCandidate` 属于一个 tenant、一个源 Case 和一个 `VERIFIED_RESOLVED` CaseVerification；唯一键阻止重试重复创建。
- 自动创建只保存来源引用和空内容，不复制原始客户消息、客户标识、设备序列号、Agent 推理或未经核验事实。
- SUPPORT/ SUPERVISOR/ADMIN 客服可以在同租户查看和撰写候选；仅 SUPERVISOR/ADMIN 可以批准、拒绝或撤销。客户、其他租户均不可见。
- 撰写内容为结构化的 title、issue_type、applicable_models、symptoms、required_evidence、steps、success_criteria、failure_exit；不含执行代码、业务授权或模型推理。
- 审批只允许 `DRAFT -> PENDING_REVIEW -> APPROVED|REJECTED`；拒绝后可修订重提；批准内容只读，撤销后不可再改动或重新提交。每次审核决定追加写入 ExperienceReview。
- 已批准经验始终是参考案例，不是事实或规则。经验审核不能验证 DeviceFact、执行 Action、批准售后动作或修改 Skill/SOP。

## 触发与服务路径
- `VerificationService.record` 只有决策为 `VERIFIED_RESOLVED` 时，在核验事务中新增候选。
- 候选建档为纯数据库操作，不新增对话路径 LLM 调用，也不经 conversation Outbox/SSE 发布。
- 客服通过真实 FastAPI 路由读取、编辑、提交审核、批准/拒绝/撤销；需要 expected_version 与 decision_id 幂等。
- Agent Context Builder 只查询同租户 APPROVED 候选；首版要求源/目标设备型号已 VERIFIED 且型号命中，来源 Case 仍解决且来源核验仍是最新核验，并通过关键词命中排序，最多注入 2 条、优先裁剪并受上下文预算限制。
- Agent 提示明确经验可能过时或不适用；需以当前 Case 的证据和手册为准。经验不得更改工具权限。

## 验收
- 未解决/不确定核验不创建候选；VERIFIED_RESOLVED 创建一条；重复提交核验不重复创建。
- 关键租户复合外键、客服角色、审核状态转移、重复 decision_id/冲突和过期版本列入 PostgreSQL 集成验收。
- 未批准、已撤销、错误型号、未知设备型号、跨租户经验不能进入 Agent context。
- Approved 候选仅为内部上下文，不出现在客户 API、消息或公开 SSE。
- SQLite/Mock 不作为迁移验收；在可用 PostgreSQL 上测试升级和模型约束。

## 明确不包含
自动 LLM 总结、自动 Skill/SOP 发布、跨租户经验共享、向量数据库、前端客服审核界面、原始对话/CoT 存储。
