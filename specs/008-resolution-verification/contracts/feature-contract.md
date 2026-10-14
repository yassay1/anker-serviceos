# 阶段 4：模拟动作的结果核验

状态：首个动作语义、审批角色及解决条件已由用户确认。此切片只适用于开发/测试环境 Mock 售后服务。

- 每次 `MOCK_SERVICE_REQUEST` 在申请时冻结一版 Resolution Contract：“模拟服务请求收到成功回执”及“客户明确确认问题已解决”。迁移会给已有模拟动作补同一版条件；后续动作产生新的 Contract，核验始终针对最新动作。
- 客户本人提交 `WORKING`、`NOT_WORKING` 或 `UNCERTAIN` 观察；客服只读，不能替客户确认。可引用本 Case 的公开且结构检查通过的图片，但图片本身不是必需的解决条件。
- 只有最新动作具备 `SUCCEEDED` 模拟回执且客户提交 `WORKING`，服务端才在同一事务保存 `VERIFIED_RESOLVED`、更新 Case 为 `RESOLVED` 并发出公开状态事件。`NOT_WORKING` 将 Case 留在 `IN_PROGRESS`，`UNCERTAIN` 或缺少成功回执保持待核验。
- 请求含 Case 版本、Contract 版本和客户端核验编号；相同编号/内容幂等返回原结果，内容变化 409。客户、租户、证据和 Case 所有权每次重验。旧客服状态接口仍不能绕过核验。
- 成功 Mock 回执只证明模拟服务请求，不证明维修、退款、保修或真实 Anker 操作，也不能单独把 Case 标为已解决。

未覆盖后续跟进、Device 可信事实归档、多模态理解、恶意内容扫描与真实外部服务。
