# Data model

## Existing authority

Conversation、Case、DevicePassport、AgentRun、MessageJob、OutboxEvent、ActionRecord、ResolutionVerification、FollowUpJob 沿用现有迁移及租户约束。不会将 UI 或模型输出作为状态真相。

## SkillDefinition (versioned static registry)

Fields: skill_id, version, title, description, availability (AVAILABLE/PREPARED), input_schema, output_schema, applicability, allowed_tools, allowed_ui_components, risk_level, failure_exit。

技能发现先确定性过滤会话状态及允许范围，再交给模型选择；未知 id/version 拒绝，PREPARED 不可调用。不支持外部动态代码。

## Skill execution records (AgentRun.result_payload)

Fields: skill_id/version, status (LOADED/COMPLETED/REJECTED), source_message_ids, execution_key, timestamps, bounded structured output。记录仅 INTERNAL，同一 run/key 幂等。LOADED 不表示任务完成。写入必须验证 tenant、conversation、active run 和 MessageJob lease。

## EmotionAssessment (prepared contract)

Fields: category enum, intensity [0,1], confidence [0,1], uncertainty, evidence message references, recommended_strategy enum (neutral/empathetic/concise/offer_human)。依据为可授权的用户消息引用及短摘要，不接受原始推理字段。判断始终为未核验辅助信号，无退款/换货/关单权限。

## Execution progress

沿用 OutboxEvent/ConversationEvent，公开 payload 只允许 run_id、stage 和固定摘要、发生时间，不包含工具参数、消息原文、内部草稿或推理；按 run、stage 与尝试幂等记录。阶段表示检索开始/结束、等待证据、等待审批、完成或失败，不等于 Case 解决。

## Readiness

只读动态状态，不新增业务事实。组件 database/schema/auth/storage/provider 分别记录 ready/not_configured/unavailable；配置齐全不代表 Provider 实测通过。
