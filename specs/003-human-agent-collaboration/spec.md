# Feature Specification: Human and Agent Collaboration

## User Scenarios & Testing

### User Story 1 - 申请与接管 (P1)

客户或客服请求真人协助，客服基于当前版本接管任务。两名客服同版本接管时只有一人成功。任务的责任归属与会话发言策略分开。

### User Story 2 - 切换策略 (P1)

客服切到 CO_SERVICE 或 HUMAN_LEAD，Agent 已开始的工作在完成时按最新策略决定可见性；HUMAN_LEAD 只允许内部 Agent 输出。客服可以恢复 AI_LEAD。

### User Story 3 - 审阅草稿 (P1)

客服查看内部 Agent 草稿并批准或拒绝；拒绝不会执行动作。审批公开文案时仍须再次核对最新会话策略。

## Requirements

- **FR-001**: 请求、分配、接管均持久化、可审计并受租户权限与版本控制。
- **FR-002**: 模式与 reply policy 原子切换，HUMAN_LEAD 强制 HUMAN_ONLY，过期版本返回冲突。
- **FR-003**: 公开发布逐次复核最新策略；内部 Agent 工作可在人工主导时继续。
- **FR-004**: 草稿决定幂等且拒绝不会触发执行；批准也不等于外部动作完成。

## Success Criteria

- **SC-001**: 并发同版本接管恰好一人成功。
- **SC-002**: 人工主导期间零条未经授权 Agent PUBLIC 消息。
- **SC-003**: 拒绝草稿后零条外部动作执行记录。

## Assumptions

本阶段审批对象为内部 Agent 文案与提案；外部售后动作执行属于阶段 4。
