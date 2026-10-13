# V1 接口提案

[完整 OpenAPI 提案](openapi.yaml)是前后端并行开发阶段 4 的共同接口目标，不是当前可调用 API。每个操作都有 `x-serviceos-status`：`implemented` 来自真实 [OpenAPI](../../openapi.json)，`planned` 只存在于[计划增量](planned.yaml)。本目录不会被 FastAPI 注册，也不生成应用正在使用的 `frontend/src/api/schema.d.ts`。

## 生成与检查

在仓库根目录运行：

```powershell
uv run --project backend --locked python contracts/proposed/v1/sync_implemented.py
uv run --project backend --locked python contracts/proposed/v1/sync_implemented.py --check
cd frontend
npm exec -- openapi-typescript ../contracts/proposed/v1/openapi.yaml -o "$env:TEMP\serviceos-proposed-v1.d.ts"
```

脚本从真实 `contracts/openapi.json` 复制现有操作及 Schema，与 `planned.yaml` 合成完整提案；若计划操作已成为真实路由，会要求先处理重叠项。`--check` 检查源同步、operationId 和 Schema 引用。临时生成的 TypeScript 类型仅用于验证提案能被前端工具读取，不替换活动 Client。真正实现一个计划接口时，先由后端应用服务、路由、Schema 和测试落地，再导出真实 OpenAPI；从 `planned.yaml` 移除对应操作并更新实际前端 Client。

## 待产品与接口评审确认的 V1 选择

四份 V1 基线决定业务对象和安全规则，但没有给以下操作级细节。下表是第一条阶段 4 纵切面的拟议取值，均未获得产品最终确认：

| 选择 | 提案中的具体值 | 评审重点 |
|---|---|---|
| 图片证据 | `multipart/form-data` 直接上传 JPEG/PNG/WebP，单文件不超过 10 MiB；先返回待安全检查状态 | 本地文件适配器与以后 S3 方案的迁移；拒绝与清理策略 |
| 模拟售后动作 | 第一种 `action_kind` 为 `MOCK_SERVICE_REQUEST`；批准与执行分离，仅 `MOCK` 回执可证明模拟操作结果 | 具体演示业务语义、审批角色和 Rule |
| 结果核验 | 服务端提供冻结的 Resolution Contract；客户或客服提交观察结果，服务端决定 Case 能否解决 | 成功条件、证据要求和失败后继续服务 |
| 后续跟进 | 客户显式同意产生 consent 记录，客服凭该记录安排任务 | 同意的有效期、撤回与取消规则 |

这些是**待确认的设计提案**，不是现有后端能力，也不是已获得真实 Anker 操作权限。前后端可据此评审和准备不提交业务结果的界面；涉及上述取值的行为须在产品、前端、后端和集成负责人审阅成功、拒绝、幂等、旧版本和恢复分支后，才标记“契约已确认”并接入真实业务流程。未确认的具体业务规则不得用客户端猜测补齐。

## 与已实现接口的关系

- 阶段 0–3 的 31 个实际路径完整复制，保持当前请求、响应及操作 ID；`/proposals/{id}/decision` 是现有内部草稿决策。
- 计划中的 `/approvals/{id}/decisions` 是阶段 4 的**外部动作审批**，不替换上述草稿决策。审批通过不会立即返回动作成功；Worker 执行和 `MOCK` 回执另行持久化。
- 计划中的 Case 证据、动作、Resolution Contract、核验、跟进、Case 任务和 Agent Run 读取尚无真实路由。客服和客户的 PUBLIC/INTERNAL 投影须在应用服务按最新权限过滤。
- 阶段 2 的真实 Provider 多轮、结构化工具兼容性和强制终止恢复仍保持待验；本提案不能改变验收状态。
