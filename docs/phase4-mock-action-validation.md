# 阶段 4 增量：模拟售后动作验证

日期：2026-10-14。范围：第一种 `MOCK_SERVICE_REQUEST`，仅开发与测试环境。业务语义、主管审批规则仍属待产品确认的拟定契约；不代表真实 Anker 售后操作。

## 实际能力

- `CaseAction`、独立审批与持久 `MockServiceOperation` 用不同记录表达申请、批准和执行回执。申请与审批均有幂等键和版本校验，不能自批。
- Worker 仅领取批准动作；回执未知时不重发，只查持久 Mock Adapter。客户只读状态和 `MOCK` 回执，内部原因与审批只向同租户客服提供。
- `/cases` 展示角色化动作与审批。网络结果不明时，同一标签页保存原请求/决定编号供手动重试，不自动重放。
- 生产配置拒绝模拟 Adapter 和模拟动作 API。当前没有真实售后接口、正式核验或跟进。

## 验证

- PostgreSQL 后端全套回归：`91 passed`，其中动作文件 `6 passed`，覆盖并发、权限、幂等、审批、回执丢失与 UNKNOWN 对账。
- 空库从基础迁移到 `0010_mock_service_actions`，`alembic check` 输出 `No new upgrade operations detected`。
- OpenAPI 导出与提案同步、前端生成 Client、`check:api`、TypeScript 类型和构建通过。
- 受控浏览器原有 31 项通过；真实 API 浏览器 3 项通过，其中新路径完成客服申请、主管审批、独立 Worker 处理和客户安全投影。

## 留待后续

正式 Resolution Contract/结果核验、客户授权的 Follow-up、Device 可信事实归档、图片上传界面与多模态、安全内容扫描、生产对象存储和真实 Provider 验收仍待后续切片。不能把模拟服务请求成功回执直接当成 Case 已解决。
