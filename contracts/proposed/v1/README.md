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

## 阶段 4 产品选择与待确认项

四份 V1 基线决定业务对象和安全规则。用户已确认首个动作语义、审批角色及解决条件；图片阈值与后续跟进规则仍待确认：

| 选择 | 提案中的具体值 | 评审重点 |
|---|---|---|
| 图片证据 | `multipart/form-data` 直接上传 JPEG/PNG/WebP，单文件不超过 10 MiB；先返回待安全检查状态 | 本地文件适配器与以后 S3 方案的迁移；拒绝与清理策略 |
| 模拟售后动作（已确认） | 第一种 `action_kind` 为 `MOCK_SERVICE_REQUEST`，仅模拟提交服务请求；另一名主管或管理员审批，申请人不能自批；批准与执行分离 | Mock 回执绝不代表真实 Anker 操作 |
| 结果核验（已确认） | 服务端冻结“模拟成功回执＋客户明确确认”两项条件；客户本人提交观察结果，服务端决定 Case 能否解决 | 失败、拒绝、UNKNOWN 和客户未确认都不能解决 |
| 后续跟进 | 客户显式同意产生 consent 记录，客服凭该记录安排任务 | 同意的有效期、撤回与取消规则 |

图片大小、格式、扫描阈值与后续跟进细节仍是**待确认提案**。已确认的动作和核验规则只适用于开发/测试环境的 Mock 服务，不授予真实 Anker 操作权限。前后端仍须依据实际 OpenAPI 和应用服务处理成功、拒绝、幂等、旧版本与恢复分支；未确认的图片与跟进规则不得用客户端猜测补齐。

## 与已实现接口的关系

- 已实现操作来自实际 OpenAPI；`/proposals/{id}/decision` 是现有内部草稿决策。
- 已实现的 `/approvals/{id}/decisions` 是阶段 4 **模拟售后动作审批**，不替换上述草稿决策。审批通过不会立即返回动作成功；Worker 执行和 `MOCK` 回执另行持久化。
- 图片证据、模拟动作、Resolution Contract 与核验已有真实路由；跟进、Case 任务和 Agent Run 读取仍只在计划增量。客服和客户的 PUBLIC/INTERNAL 投影须在应用服务按最新权限过滤。
- 阶段 2 的真实 Provider 多轮、结构化工具兼容性和强制终止恢复仍保持待验；本提案不能改变验收状态。
