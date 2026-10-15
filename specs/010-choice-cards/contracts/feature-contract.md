# 功能契约：可点击选项卡（ChoiceGroup）

> 拟定契约，不是已实现的 OpenAPI，也不是功能完成证明。契约状态：**草案**（2026-10-15）。

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 所属阶段、功能切片 | 阶段 4 遗留项「用户侧身份/证据/步骤/核验/风险卡完整纵切面」（`docs/development-plan.md:72`）的第一个切片。不在阶段 5 范围。 |
| 用户目标与入口 | 客户在 `/support` 的会话里看到 Agent 给出的**可点击选项**，点一下就把该选项作为自己的回复发出，不必手打。入口：会话中「服务交互卡」区域。 |
| 涉及对象及关系 | 只涉及 Conversation 与 AgentRun。**不**创建 Task、**不**改 Case、**不**改 Device 事实。选项点击产生的是一条普通客户消息。 |
| 前端负责人 / 后端负责人 / Agent 负责人 | 同一执行者（本仓库单人开发）。 |
| 集成负责人 | 待确认（跨前后端切片，按 `docs/contributing.md` 需要一个确认人）。 |
| 契约状态与版本 | 草案 v1。`CATALOG_VERSION` 由 1 升到 2，前端同时接受 1 与 2。 |

## 2. HTTP 操作

**本切片不新增任何 HTTP 操作。** 这是刻意的选择，也是本契约最重要的一条：

- 选项点击复用已存在的 `POST /api/v1/conversations/{id}/messages`（`SendMessage`）。
- 因此服务端已有的校验全部继续生效：身份与租户、会话 ACTIVE、Case 关联、`client_message_id` 幂等、`expected_*` 版本冲突。
- **不**新增 UI action intent，**不**放宽 `ui_catalog.py` 里「非 ActionBar 类型不得携带动作」的限制，**不**触碰 `UIActionRequest.action_id` 的 `Literal`。
- 唯一变化的是 UI 文档的响应体：`UIComponent` 增加可选 `options` 字段（见第 3 节）。

理由：客户点选项与手打一句话在业务上是同一件事。让它走消息通道，就不需要在最安全敏感的动作白名单上开口子。

## 3. 事件、异步与投影

- **提案来源**：Agent 的最终 JSON 增加**可选** `options`。服务端逐项校验后才允许进入投影；任一项不合法则整个提案判废并降级为文本（沿用现有 `ui_fallback_code = "ui_proposal_invalid"` 语义）。

  | 字段 | 约束 |
  |---|---|
  | `options` | 可选；2–5 项 |
  | 每项 `label` | 非空字符串，≤40 字，经现有 `UNSAFE` 正则拒绝 `< > http(s): javascript: data:` 与 `on*=` 事件属性 |
  | 每项 `value` | `^[a-z0-9-]{1,32}$`，稳定 slug，不允许自由文本 |
  | 去重 | `label` 与 `value` 各自不得重复 |

- **投影**：`publish_ui_projection` 首次真正读取提案内容。提案带合法 `options` 且 audience 为 CUSTOMER 时，追加一个 `ChoiceGroup` 组件（id `agent-choice`）；否则维持现有 `QuestionForm`。
  - 组件位置：**必须排在客户文档的 `ActionBar` 之后**（`backend/tests/test_business_api.py` 钉死 `components[0].type == "ActionBar"`）。
  - `ChoiceGroup` 的 props 仍为 `("title", "body")`，选项放在组件级 `options` 字段，**不塞进 props**——props 的值一律是字符串且前端按字符串校验，塞数组会让整份文档判废。
  - `data_source` 沿用 `AGENT_RUN_VIEW` / `question`，`actions` 为空（不允许携带动作）。
- **版本**：`CATALOG_VERSION` 升到 2。前端 `catalog_version` 接受 `{1, 2}`，这样体验库里已有的 v1 文档不会被新前端判废。
- **降级**：目录里没有的类型、`options` 越界、revision 过期、文档过期或版本回退时，沿用现有整文档降级（显示 `刷新交互卡`，文字消息始终可用）。
- 不新增事件类型；`ui.document.published` 与 `ui.action.accepted` 不变。

## 4. 两端验收

| 路径 | 预期的服务器事实与页面表现 | 证据/测试负责人 |
|---|---|---|
| 成功 | 提案带合法 `options` → 文档含 `ChoiceGroup`（在 ActionBar 之后）→ 客户点一项 → 产生一条 CUSTOMER/PUBLIC 消息 → Agent 回话并刷新卡片 | `backend/tests/test_ui_catalog.py`、`frontend/tests/delivery-readiness.spec.ts`、真实浏览器手测 |
| 无权限或跨租户 | 客户文档不得出现 `CASE_VIEW`/`TASK_VIEW` 来源；客服文档不出现客户 `ChoiceGroup` | 现有 `validate_components` 断言保持 |
| 输入不合法或风险拒绝 | 选项少于 2 项、多于 5 项、label 含标签/URL、value 非 slug、label 或 value 重复 → 提案判废、退回文本，不发布卡片 | `backend/tests/test_agent_result.py` |
| 重复请求与并发竞争 | 同一修订提交后禁用再次点选；回执未知时待发送消息保留原 `client_message_id`，从消息列表用原请求重试，服务端幂等复用 | `frontend/tests/delivery-readiness.spec.ts` 同键重试用例 |
| 过期版本 | 文档 revision 回退或已过期时选项禁用，只能回到文字路径 | `frontend/tests/delivery-readiness.spec.ts` |
| 断线、超时与恢复 | 提交失败时显示待发送消息和可读错误，保留原请求供手动重试；文字路径始终可用 | 同上 |

## 5. 变更与落地记录

- 契约确认者和日期：**待确认**（本切片由单一执行者完成，需人工复核后才能转「已确认」）。
- 确认后的变更、原因、影响方与通知记录：无。
- 实际路由、Pydantic Schema、OpenAPI、前端生成 Client 对照：
  - **没有新增路由**。选项点击复用 `POST /api/v1/conversations/{id}/messages`。
  - `UIComponent` 增加可选 `options`，新增 `UIOption`（`contracts.py`）；`contracts/openapi.json` 与 V1 提案已重新生成，`frontend/src/api/schema.d.ts` 已重新生成，`check:api` 通过。
- 本地命令与结果：
  - 后端 `pytest --require-postgres`：**192 passed**（改动前 170，新增 22 条，覆盖提案选项边界、目录选项规则、投影选择）。
  - 浏览器 `npm run test:browser`：**68 passed**（改动前 60，新增 8 条）。
  - `export_openapi --check`、`sync_implemented.py --check`、`check:api`、`typecheck`、`build` 全部通过。
  - 真实模型 + 真实浏览器：模型产出 4 个选项 → 投影为 `catalog_version 2` 的 `ChoiceGroup`（ActionBar 仍居首、无动作）→ 点第一项 → POST 202 → 该选项作为 CUSTOMER/PUBLIC 消息落库 → Agent 继续回话。
- 未通过项：Playwright 托管 webServer 在本机不稳定（见 `docs/phase5-validation.md`），浏览器与 live 验收以自托管服务方式执行；`npm run test:live` 的既有 6 条未改动。
- 对 `docs/development-plan.md` 勾选的影响：**不改**。第 72 行那条是「身份/证据/步骤/核验/风险卡完整纵切面」的整体任务，本切片只做了采集卡里的一个类型，整行仍不勾选。
