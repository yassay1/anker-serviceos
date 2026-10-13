# Feature Specification: Persistent Conversation Events and SSE Recovery

## User Scenarios & Testing

### User Story 1 - 可恢复的更新 (P1)

客户与客服在连接中看见已保存消息与协作变化；断线后按最后序号补取，不丢消息、不重启 Agent。

### User Story 2 - 可见性隔离 (P1)

客户不能从历史接口或事件流读取内部备注、草稿、任务及内部 UI；客服只能读同租户会话。

## Requirements

- **FR-001**: 事件有会话内单调 sequence，持久化并可按 sequence 补取。
- **FR-002**: 每次读与流式补取均按当前身份、租户及 PUBLIC/INTERNAL 可见性过滤。
- **FR-003**: SSE 断线可重连，不启动或取消 Agent Run。
- **FR-004**: 所有公开事件通过 Conversation Service 写入和读取，流中不包含原始推理或内部载荷。

## Success Criteria

- **SC-001**: 断线前后消息 ID 全部可从持久存储恢复且仅一份。
- **SC-002**: 客户对内部事件的读取结果始终为空。

## Assumptions

SSE 用于低延迟通知；消息列表仍是权威内容，断线后重新查询。
