# Feature Specification: Controlled UI Documents and Intents

## User Scenarios & Testing

### User Story 1 - 安全展示 (P1)

客户与客服在固定页面中看到当前会话的版本化交互投影；不支持的组件或过期数据降级为文本和固定输入。客服可见内部摘要，客户无法读取内部 UI。

### User Story 2 - 低风险动作 (P1)

客户从受信卡片请求人工协助；服务端再次核验 actor、UI revision、会话版本和幂等键。旧卡片与越权请求拒绝，成功只创建人工任务，不声称完成外部售后动作。

## Requirements

- **FR-001**: UIDocument 有稳定 ui_id、单调 revision、schema/catalog version、audience、visibility、状态及 fallback_text；旧版留痕且不可操作。
- **FR-002**: Catalog 严格限制组件、字段、长度、动作、数据源；未知类型、URL、代码和越权引用安全拒绝。
- **FR-003**: `/support` 与 `/desk` Renderer 只实现受信组件，未知或不兼容时安全降级，保留文字消息入口。
- **FR-004**: 公开 UI 经 Conversation Service 最新模式和发言策略授权；INTERNAL UI 不向客户返回或推送。
- **FR-005**: UI action intent 仅允许已实现的请求人工协助应用命令，重新鉴权、检查 revision/业务版本与幂等，保存调用审计。

## Success Criteria

- **SC-001**: 旧 revision、未知组件、越权数据源和跨租户读取全部被拒绝或降级。
- **SC-002**: 同一动作键相同输入只创建一个任务，冲突输入返回 409。
- **SC-003**: 文本消息与固定表单在 UI 不可用时仍可使用。

## Assumptions

阶段 3 仅实现服务端生成的安全投影与低风险协助意图；上传、核验、外部动作执行和回执卡属于阶段 4。
