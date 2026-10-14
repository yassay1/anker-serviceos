# 阶段 4 切片：模拟售后请求与可核验回执

状态：首个动作语义与审批角色已由用户确认。此切片只模拟“提交一次售后服务请求”，不申请真实维修、退款或保修，也不调用 Anker 系统。

## 目标与边界

- 授权客服对自己的租户内、未关闭的 Case 请求 `MOCK_SERVICE_REQUEST`。Agent 的 `ACTION` 草稿仅供参考，不能直接执行。
- 每次请求生成独立 `ActionRecord` 和待审批记录；审批与执行分离。只有另一名具备 `SUPERVISOR` 或 `ADMIN` 角色的客服能批准或拒绝。申请人不能自批。
- 独立 Worker 领取批准的动作，经明确标记的持久 Mock Adapter 获取回执。批准本身不表示成功；`SUCCEEDED` 或 `FAILED` 只能由 Adapter 回执确认。
- 调用后结果不确定时进入 `UNKNOWN`，只能按相同幂等键查询 Adapter 结果；不得重新提交。无法对账的记录保持 `UNKNOWN` 供人工处理。
- 客户可查看本人 Case 的安全状态与明确 `MOCK` 回执；申请原因、审批身份和内部错误只对同租户客服开放。重要变化记录内部 Outbox，前端仅展示服务端状态。

## 操作与并发

- `POST /api/v1/cases/{id}/action-requests`：`client_action_id`、`expected_case_version`、`action_kind=MOCK_SERVICE_REQUEST`、可选 `source_proposal_id`、`reason`。相同 Case + client ID + 内容复用原记录；内容不同返回 409。新动作要求最新 Case 版本，创建成功返回 202 与 `WAITING_APPROVAL`。
- `GET /api/v1/cases/{id}/actions`、`GET /api/v1/actions/{id}`：每次重验 Case 所有权与租户；客户只得到公开投影。
- `GET /api/v1/cases/{id}/approvals`：仅授权客服。`POST /api/v1/approvals/{id}/decisions`：`decision_id`、`expected_version`、`APPROVED|REJECTED`、`reason`。相同 decision ID + 内容复用；不同内容 409。重复或过期审批不会再次排队。
- `ActionRecord` 终态增列 `REJECTED`，明确区分人工拒绝和 Adapter 返回 `FAILED`；该差异需同步真实 OpenAPI 和提案。

## 验收门槛

同租户成功请求、另一人审批、Worker 得到 `MOCK` 回执；客户/跨租户拒绝；申请人与审批人隔离；过期版本和幂等冲突；审批拒绝不执行；Adapter 失败返回 `FAILED`；超时后按键对账不重复执行；进程中断后恢复；真实 OpenAPI、生成 Client、PostgreSQL 迁移与回归通过。

未覆盖图片多模态、真实外部 API、正式结果核验、跟进和 Device 事实归档。这些依次在后续阶段 4 切片中实现。
