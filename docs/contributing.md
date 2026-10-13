# 协作开发指南

本指南说明当前仓库如何拆分和集成工作。产品规则以[产品定义](product-definition.md)、[系统架构](architecture.md)、[领域与接口契约](domain-and-contracts.md)、[开发实施计划](development-plan.md)四份 V1 文档为准；完成状态结合计划勾选和阶段验收记录判断。开始任务时先查实际代码及[现有项目合并说明](baseline-integration.md)，将设计目标与现有能力分开记录。

## 当前工作面

| 工作面 | 活动入口 | 变更时共同核对 |
|---|---|---|
| 业务数据与迁移 | `backend/serviceos_api/persistence/`、`backend/migrations/` | Case、Conversation、Device 的独立性、租户约束、版本与升级路径 |
| 应用服务与权限 | `backend/serviceos_api/application/` | 资源授权、业务状态、幂等及公开消息发布边界 |
| HTTP 契约 | `backend/serviceos_api/api/`、`backend/serviceos_api/application/contracts.py` | 路由与 Schema 真实存在，错误语义与 OpenAPI 一致 |
| Agent 与异步执行 | `backend/serviceos_api/agents/`、`backend/serviceos_api/worker/` | Worker 租约、Checkpoint、应用服务写入和恢复时的副作用 |
| Web | `frontend/src/` | 当前 API 类型、用户/客服可见性、失败与重试状态 |

这是现有文件位置，不表示每个领域已经有独立模块。当前 `api/business.py` 与 `application/services.py` 包含多个业务对象；拆分时保持原有服务校验和路由契约，避免产生第二套规则。已归档原型不参与活动实现。

## 拆分任务与并行工作

1. 每项工作写明所处阶段、验收场景、拟改文件、依赖及一个集成负责人。可独立处理的界面、后端业务和文档任务可并行；共享 Schema、迁移、路由和生成契约的改动先约定字段、错误、权限与版本，再分别实现。
2. 跨 Case、Conversation、Device 的写操作由应用服务维护不变量；Agent 工具只调用类型化服务命令。用户可见消息和公开事件由 Conversation Service 检查当前协作策略与可见性。接口审阅同时核对成功、拒绝、重复请求与过期版本路径。
3. API 变更先实现路由、Pydantic Schema 和应用服务及对应测试，然后导出 `contracts/openapi.json`，再运行 `frontend` 的 `generate:api` 并接入页面。目标接口仅写在 V1 设计表中时，前端任务应以明确的依赖等待该接口，不添加假成功端点。
4. 迁移、权限策略、状态机和公开事件格式属于共享边界。并行分支变更同一边界时，由集成负责人先合并并验证契约，再让依赖方更新到新版本；冲突按 V1 业务规则和实际测试解决，不按文件时间先后覆盖。

## 变更集成

- 一个变更集说明目标、涉及的业务边界、实际改动文件、验证命令及结果、未实现项。修改设计时同步标注计划状态；只有满足阶段验收且有记录才勾选完成。
- 提交前运行受影响的后端测试、OpenAPI 漂移检查、前端生成类型检查与构建；具体命令见 [README 的校验段](../README.md#校验与契约生成) 和 `.github/workflows/ci.yml`。跨服务或迁移的改动须检查失败、并发与恢复路径。
- GitHub 仓库已建立；合并流程可使用短期分支和 PR 让相关边界的维护者审阅，等 CI 实际通过再合并。当前 CI 配置不证明每次远端运行已成功，也尚未配置 CODEOWNERS 或分支保护；将来明确维护者与权限后再启用这些规则。

外部依据及本项目的取舍见[参考资料](references.md)。本项目采用适合现有代码的最小流程，不引入 KEP、强制 CODEOWNERS 或额外技术栈。
