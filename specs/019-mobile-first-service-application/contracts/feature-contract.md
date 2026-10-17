# 功能契约：手机优先服务界面与真实关联读取

> 状态：已按本任务实现并通过验收；接口以 `contracts/openapi.json` 和 FastAPI 路由为准。原型本身仍只是静态设计参考。

## 1. 场景与业务对象

| 项目 | 内容 |
|---|---|
| 功能 | 将 4189 手机优先双端评审稿的主要流程接入现有应用 |
| 客户入口 | `/` 进入服务、历史 Conversation、Service Case 服务记录；`/support` 对话/处理详情/关联设备 |
| 客服入口 | `/desk` 人工任务 OPEN/MINE 队列、客户会话和服务资料；Case 队列保持独立 |
| 对象关系 | Case、Conversation、Device Passport、Service Task、Agent Run 各自独立；Case↔Conversation 和 Case↔Device 使用已有多对多关系 |
| 写操作 | 除明确新建会话、发送、请求协助、任务认领及既有草稿/Case/设备操作外，不新增业务写操作 |
| 数据迁移 | 预计无需迁移；`case_conversations`、`case_devices` 已存在 |

## 2. 新增只读 HTTP 契约（已实现）

### 2.1 客户/客服读取会话关联案例

- 方法与路径：`GET /api/v1/conversations/{id}/customer-cases`。
- 成功：`200`，返回 `CustomerCaseLinkRead[]`；每项包含 `case: CaseRead` 与 `device_ids: UUID[]`。只包含当前仍关联且未归档的 Case，以及仍存在且未归档、对当前调用者可读的关联 Device ID。不含 Case Evidence、内部备注、客服专用事实摘要或模型推理。
- 授权：Conversation 必须由当前 actor 在当前 tenant 资源授权范围内可读；CUSTOMER 仅本人 Conversation/Case；STAFF 仅同 tenant，且关联 Case 的客户归属必须与 Conversation 一致。读取关联不修改版本或事件。
- 空态：没有关联 Case 时返回 `[]`；有关联 Case 但没有设备时该项 `device_ids: []`。
- 错误：认证失败沿用现有 401；资源不存在或无权读取统一 404；服务不可用沿用现有 API 错误，不返回空数组伪装成功。
- 分页/排序：返回全部当前可读关联，按 `case.created_at ASC, case.id ASC` 排序；此视图对应关系通常较小，不分页、不截断。
- 幂等/版本：GET 无写副作用，不适用。

### 2.2 客户/客服读取案例关联会话

- 方法与路径：`GET /api/v1/cases/{id}/conversations`。
- 成功：`200`，返回 `LinkedConversationRead[]`；每项仅含 `id, title, status, created_at`。`title` 继续复用现有 Conversation 标题投影，只根据首条公开客户消息生成；客服内部消息不参与。不得暴露 `collaboration_mode`、`reply_policy`、内部活动、草稿或消息内容。
- 授权：Case 必须由当前 actor 在当前 tenant 资源授权范围内可读；仅返回其真实 `case_conversations` 关联且客户归属相同、当前调用者有权读取的 Conversation。CUSTOMER 仅本人资源；STAFF 仅同 tenant。
- 空态：没有关联 Conversation 时返回 `[]`。
- 错误、排序、分页、写入语义同 2.1；排序为 `conversation.created_at DESC, conversation.id ASC`，返回全部可读关联，不截断。

## 3. 页面行为契约

- 首页“进入对话”仅导航，不调用 create API；“新对话”只有在用户明确点击后才创建 Conversation。历史对话读取 Conversation 列表，服务记录读取 Case 列表。
- 客户工作区三个视图分别为对话、处理详情、关联设备。Case/设备视图只展示 2.1 的关联与既有资源端点返回的授权字段；Case 无设备、无关联案例、设备身份未知或事实未核验时说明真实空态。
- 客户返回 Case 详情时，由 2.2 的关联列表展示一至多个会话；不能选择不存在的“唯一所属会话”。
- 客服手机任务队列调用已有 `GET /api/v1/tasks?queue=OPEN|MINE`。OPEN 与 MINE 继续按 task 契约排序、过滤和分页；认领使用已有 `expected_version`。Case 队列调用 `GET /api/v1/cases`，独立展示 Case 状态，不与 task 合并或映射。
- 客服时间线只展示持久且有权限的消息；回复草稿标明“未发送 · 仅客服可见”。插入、编辑、审批均不创建客户消息；独立发送通过现有 Conversation Service 当前策略复核，以 `MessageReceipt` 和持久公开消息确认成功。
- 连接状态、AgentRun 和 Worker 进度不得表现为 Case 结果；不显示缺少接口支持的 presence、等待时间、SLA、ETA 或满意度提交。
- 事件/SSE 是刷新提示，查询快照为权威来源；403 停止重试，404 不泄露资源存在性，409 刷新后交给操作者决策，超时使用既有相同幂等 key 对账。

## 4. 预计实现边界

| 面 | 预计位置 | 状态 |
|---|---|---|
| Pydantic 读 Schema | `backend/serviceos_api/application/contracts.py` | 已实现 `CustomerCaseLinkRead`、`LinkedConversationRead` |
| Case/Device/Conversation 关系读取 | `backend/serviceos_api/application/business.py` | 已实现，复用资源授权和持久多对多关系 |
| HTTP GET 路由 | `backend/serviceos_api/api/resources.py` | 已实现两个只读 GET 路由 |
| 后端回归 | `backend/tests/test_business_api.py` | 已覆盖授权、跨租户、空关系和多对多关系 |
| OpenAPI/Client | `contracts/openapi.json`、`frontend/src/api/schema.d.ts`、`frontend/src/api/client.ts` | 已导出、生成并通过一致性检查 |
| 前端 | `CustomerHome.tsx`、`ConversationWorkspace.tsx`、`CaseConversationPicker.tsx`、`CasesWorkspace.tsx`、`StaffTaskQueue.tsx`、相关样式和浏览器测试 | 已接入真实 API；既有业务写流程继续复用 |

未新增数据库迁移：现有 `case_conversations` 和 `case_devices` 关系足以支撑读取。前端只调用生成类型对应的真实路由，不造 mock 的成功状态。

## 5. 验收矩阵

| 路径 | 预期 | 证据 |
|---|---|---|
| 成功读取 | 多 Case、多 Conversation、多 Device 按真实关系呈现；空关系显示空态 | 应用服务/API PostgreSQL 测试与浏览器场景 |
| 无权限/跨租户 | CUSTOMER 不能读他人资源；STAFF 不能读其他 tenant；统一拒绝 | API 测试与真实 live 场景 |
| 首页入口 | 点击进入服务不调用 create；显式新对话才创建 | 浏览器拦截和真实 API/DB 场景 |
| 队列归属 | OPEN 仅未分配任务；MINE 仅当前客服 active assignment；Case 状态独立 | 队列 API 与客服页面测试 |
| 认领竞态 | 版本胜者成功，败者 409 并刷新队列 | 现有 claim 集成测试及浏览器恢复 |
| 回复草稿 | 创建/编辑/审批不写客户消息；发送须当前授权且真实 receipt | 现有 draft API 测试和客户/客服联调 |
| 失败/断线 | 403 不重试；404 不泄露；409 刷新；未知结果使用原 key 对账 | 前端及隔离 PostgreSQL 测试 |
| 视口/无障碍 | 360×800、375×812、390×844、768×1024、1280×800；键盘、安全区、滚动、44px 控件、焦点/读屏检查 | 浏览器自动化和人工视口复核 |

## 6. 落地记录

- 实际 operationId：`list_customer_case_links`、`list_case_conversations`；路径分别为 `/api/v1/conversations/{id}/customer-cases` 和 `/api/v1/cases/{id}/conversations`。
- 客户首页“进入对话”是 React Router 导航，不执行 Conversation 创建；历史 Conversation 和 Case 服务记录来自各自列表 API。
- 客户工作区的 Case、Device 显示依照关联读取 API 的结果；对话、处理详情、关联设备在移动/窄平板布局中单面板切换。
- 客服窄屏入口使用 `GET /api/v1/tasks?queue=OPEN|MINE` 和现有带 `expected_version` 的 claim；`/cases` 继续使用独立 Case 列表。会话消息、设备/Case 上下文、AI 回复草稿、审批和发送均复用当前接口。
- `uv run --project backend --locked ruff check backend/serviceos_api/api/resources.py backend/serviceos_api/application/business.py backend/serviceos_api/application/contracts.py backend/tests/test_business_api.py`：通过。
- `uv run --project backend --locked pytest backend/tests/test_business_api.py -q --require-postgres`（配置本地 PostgreSQL 测试 URL）：24 passed。
- `npm run typecheck`、`npm run check:api`、`npm run build`：通过；Vite 仍提示主 JS chunk 大于 500 kB。
- `npm run test:browser`：109 passed；包括入口不创建会话、关系授权拒绝、多对多关联、客服认领与 AI 草稿发布边界、无障碍和指定五种客户视口。
- 未通过真机软键盘/安全区做原生 IME 手工验收；浏览器自动化以缩小可视高度和 safe-area CSS 为验证范围。无真实 Anker 售后 API 时，既有 Mock Adapter 继续保持模拟标识。
