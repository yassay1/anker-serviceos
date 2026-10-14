# 阶段 4 动作后解决状态保护

在正式 Resolution Contract 与结果核验服务落地前，Case 只要有售后动作记录，现有客服状态切换 API 就拒绝直接写入 `RESOLVED`。待审批、执行及 UNKNOWN 保持 `ACTION_UNSETTLED`；成功、失败、拒绝等终态返回 `VERIFICATION_REQUIRED`。这避免把 Mock 回执、失败或拒绝解释为用户问题解决。已有无动作 Case 的状态接口保持当前 V1 行为。

下一切片接入冻结的解决条件和可审计观察记录后，应由应用服务在同一事务验证条件并写入 `RESOLVED`；不得放开旧接口绕过核验。当前改动没有注册核验空路由，也没有把任何回执伪装成客户确认。

本地 PostgreSQL 定向回归覆盖模拟成功、失败和拒绝三个终态，结果为 9 项通过；完整后端回归 94 项通过。OpenAPI 导出检查、拟定契约同步检查和 `git diff --check` 均通过。远端 CI 结果以对应 PR 为准。
