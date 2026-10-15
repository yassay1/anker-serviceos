# 经验学习机制发现

## 当前实现
- 已有 CaseEvidence、CaseVerification、CaseAction、Approval、DeviceFact、AgentRun、ServiceTask 等持久化业务记录。
- `VerificationService.record` 在正式结果核验时更新 Case 并记录 `verification.recorded` 事件；可作为可靠经验候选触发点。
- `OutboxEvent` 用于会话事件发布，不适合直接复用为内部经验任务队列，避免消息可见性/发布边界混淆。
- 当前 Skill 注册表为代码内固定版本；首版经验应是被审核的案例参考，Skill/SOP 仍通过代码评审发布。
- Agent Harness V2 已从业务库装配 Case 状态、Evidence、Action/Approval、Verification、Task、Follow-up；Checkpoint 只负责单次 AgentRun 恢复。
- 当前上下文预算默认 6000 token；经验检索必须在裁剪顺序中低于当前问题、协作策略、Case状态和可信设备事实。

## 成熟机制参考（概念采用，不代表依赖引入）
- Rasa conversation-driven development：审阅真实对话、人工标注、回归测试、小步改进；代理指标不能代替人工审查。
- LangMem：区分事实、经历、程序性记忆；支持异步整理和更新历史。ServiceOS 只借鉴类型区分与后台候选整理，不允许自动改 VERIFIED 事实/SOP。
- LangGraph Store 与 Checkpointer 职责不同：跨线程长期记忆与每线程执行状态分开。ServiceOS 继续让业务库承担权威事实与审核经验存储。
- LangSmith/Agent eval：离线回归与生产异常复核闭环；本项目先用现有 pytest/PostgreSQL 和来源化测试样例，不引入 SaaS trace 上传。

## 关键约束
- 仅 `VERIFIED_RESOLVED` 的正式核验结果可提供候选依据；候选初态不等于批准。
- 跨租户学习默认禁止；要形成共享 SOP，必须人工脱敏与独立审核。
- 参考经验不转成事实，不授予工具/审批权限，不保存原始思维链或敏感客户资料。
