# 功能契约：受控图片证据

> 本文件按 `docs/templates/feature-contract.md` 记录首个阶段 4 切片。契约状态是**草案**。图片格式、10 MiB 上限和本地结构扫描阈值来自 `contracts/proposed/v1/`，产品、前端和集成负责人尚未把它们确认为最终契约。实现使用这些提案值，以便接口可以联调；不得把它们写成已冻结的产品规则。

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 所属阶段、功能切片 | 阶段 4；受控图片证据与安全检查。不包含多模态模型理解、Mock 动作、核验、跟进或设备事实归档。 |
| 用户目标与入口 | 客户在自己的 Case 上提交 JPEG/PNG/WebP，先得到“待安全检查”回执；检查通过后才能下载。`/support` 与 `/desk` 的上传界面本切片不实现，只提供真实 API。客服可查看同租户证据，并可另存 INTERNAL 图片。 |
| 涉及对象及关系 | 图片存在独立的 `case_image_evidence`，不改写阶段 1 的文本 `case_evidence`。Case 与 Conversation、Device 仍独立。检查任务是 `evidence_inspection_jobs`，不是对话 Agent Job。 |
| 前端负责人 / 后端负责人 / Agent 负责人 | 前端：待接入生成 Client。后端：本切片。Agent：不涉及；Agent 不能代替客户上传。 |
| 集成负责人 | 待指定。导出 OpenAPI 后由前端生成 Client 再联调。 |
| 契约状态与版本 | 草案，2026-10-13。图片限制与扫描阈值：**待确认**。 |

## 2. HTTP 操作

### `POST /api/v1/cases/{id}/evidence`

- 用途、方法与路径：保存图片并排队做本地结构检查。`202`，`operationId=upload_case_evidence`。
- 调用角色、租户与资源授权：已登录的 Case 客户，或同租户客服。其他客户和跨租户返回 `404`。客户提交 `INTERNAL` 返回 `403`。未登录 `401`。
- 请求字段：`multipart/form-data`。`client_evidence_id`（UUID，必填）、`expected_case_version`（整数，必填）、`visibility`（`PUBLIC`/`INTERNAL`，默认 `PUBLIC`）、`file`（二进制，必填）。
- 成功：`202`，正文为证据元数据，`inspection_status=PENDING`，`verification=UNVERIFIED`。不返回文件字节或内部拒绝码。
- 失败：`401` 未登录；`403` 客户不能提交内部图片；`404` 案例不可见；`409` `STALE_VERSION` 或 `IDEMPOTENCY_CONFLICT`，可带 `current_version`；`413` `FILE_TOO_LARGE`；`415` `UNSUPPORTED_MEDIA` 或 `MEDIA_MISMATCH`；`422` `EMPTY_FILE`；`503` 数据库不可用。已关闭案例返回 `409` `CASE_CLOSED`。
- 幂等与并发：同一 Case 内相同 `client_evidence_id` 且文件摘要与可见性相同，返回原来的 `202` 回执，不新增行、不重复排队。摘要或可见性不同返回 `409`。新图片必须匹配当前 Case 版本；同时提交两张新图片时只有一张成功。重复请求不要求版本仍是原值。
- 分页：不适用。
- 后端实现位置与当前状态：`EvidenceService.upload`、`api/evidence.py`。这是真实路由，不是假成功接口。大小上限目前按提案取 10 MiB，**待确认**。

### `GET /api/v1/cases/{id}/evidence`

- 用途：按创建时间从早到晚列出调用者可见的证据元数据。`operationId=list_case_evidence`。
- 授权：客户只看 `PUBLIC`；客服看同租户公开和内部元数据。
- 查询：`cursor` 为上一页最后一条证据 ID；`limit` 默认 50，最大 100。隐藏游标返回 `404`。
- 成功：`200`，`items` 与可空 `next_cursor`。
- 失败：`401`、`404`。只读，无幂等键。

### `GET /api/v1/cases/{id}/evidence/{evidence_id}/content`

- 用途：下载已通过检查的图片。`operationId=read_case_evidence_content`。
- 授权：每次重新检查案例、可见性和 `CLEAN`。`PENDING`、`REJECTED`、内部图片对客户、跨租户均返回 `404`，不区分原因。
- 成功：`200`，`Content-Type` 为保存的 `image/jpeg`、`image/png` 或 `image/webp`，`Cache-Control: no-store`。
- 失败：`401`、`404`。

## 3. 事件、异步与投影

- `evidence.received` 在受理事务中写入 Outbox，可见性与图片一致。关联会话各一条；没有关联会话时仍保留无会话 Outbox，不进入 SSE。
- `evidence.inspected` 只在 `PENDING` 第一次变成 `CLEAN` 或 `REJECTED` 时写入。Worker 重试已终态的检查不会再写事件，也不会改字节。
- 客户 SSE 只能看到 `PUBLIC`。内部图片事件为 `INTERNAL`。
- 检查由 `python -m serviceos_api.worker.inspection` 领取。它不调用模型 Provider。消息 Worker 在未配置 Provider 时仍然拒绝领取对话任务；配置了 Provider 时，消息 Worker 循环里也会领取检查任务。
- API 受理后立即返回 `PENDING`。未检查通过的图片不能下载。检查失败会按租约重试；用尽次数后任务失败，图片保持 `PENDING` 且不可下载。
- 不发布新的 UI Schema。文本 `CaseEvidence` 和既有 UI 投影保持原样。
- 读取案例版本、证据列表和关联会话事件即可看到新状态。

## 4. 两端验收

| 路径 | 预期的服务器事实与页面表现 | 证据/测试负责人 |
|---|---|---|
| 成功 | 一行证据、一个检查任务；检查后为 `CLEAN`，内容与上传字节一致 | 后端 `test_case_image_evidence.py`；浏览器路径待前端接入 |
| 无权限或跨租户 | 其他客户和另一租户 `404`；客户请求内部图片 `403`；未登录 `401` | 后端 |
| 输入不合法或风险拒绝 | 空文件 `422`，非 JPEG/PNG/WebP 或类型不符 `415`，超过提案大小 `413`；尾随脚本被检查为 `REJECTED` 并清除字节，下载 `404` | 后端。扫描阈值**待确认** |
| 重复请求与并发竞争 | 相同编号和摘要复用原记录；不同摘要 `409`；同一版本两张新图片只有一张成功 | 后端 |
| 过期版本 | 新图片版本不匹配时 `409` `STALE_VERSION` | 后端 |
| 断线、超时与恢复 | 检查异常后再跑一次仍只有一行；过期租约恢复后变为 `CLEAN`，不产生第二份文件 | 后端。浏览器断线待前端 |

## 5. 变更与落地记录

- 契约确认者和日期：未确认。2026-10-13 仅记录提案取值已被后端实现。
- 仍待确认：单文件 10 MiB、仅 JPEG/PNG/WebP、本地结构扫描（边长 8192、1600 万像素）是否足够；拒绝后的保留期限；已解决但未关闭的案例能否继续收图。本切片拒绝向已关闭案例追加图片。
- 与提案的差异：图片表名为 `case_image_evidence`，避免覆盖阶段 1 文本证据。响应使用 `EvidenceRead`，不使用 `Proposed*` 名称。错误在原有 `detail` 上增加稳定 `code`，旧接口不强制返回 `code`。
- 实际路由、Pydantic Schema、OpenAPI 与前端 Client：实现后导出 `contracts/openapi.json`，并从 `planned.yaml` 移除这三个操作。前端需运行 `npm run generate:api` 后接入，不能把未检查图片显示成已通过。
- 对 `docs/development-plan.md` 的勾选：不勾选。多模态理解、界面和其余阶段 4 能力都未完成。阶段 2 真实 Provider 验收保持待验。
