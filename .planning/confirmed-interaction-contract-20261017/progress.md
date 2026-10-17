# 进度

- 2026-10-17：阅读根 AGENTS.md、README、四份 V1 主基线、baseline-integration、contributing、frontend/README、backend/README。保留所有已有未提交改动。
- 已核对 OpenAPI operation/schema、前后端页面、ConversationService/BusinessService、事件/SSE、测试、活动手册和赛题参考说明。
- 已查阅 Chatwoot、Intercom、Zendesk 官方产品资料；适用原则与边界写入 findings.md。
- contract-map-draft.md 逐行记录客户/客服意图、状态、API/event、schema、服务位置、权限、visibility、幂等/version、回执/cursor、恢复、测试证据和分类。
- 曾发生 PowerShell brace、rg regex、JS 字符串错误，均改用兼容命令；未影响产品文件。
- 第一阶段没有跑测试、OpenAPI 导出、前端构建、浏览器或数据库验收，只写独立规划目录。
- 用户确认按推荐的保守业务语义推进。第二阶段新增/更新内容见 `specs/018-interaction-contract-alignment/` 与下方增量记录。
- 既有未提交工作持续保留；尤其没有改写原有 README、Agent runtime/actions、knowledge、Case 页面及既有 migration 0020 内容。

## 第二阶段实际进度（2026-10-17）

- 完成客户人工任务安全状态读取、staff OPEN/MINE 队列、持久 AI 回复草稿生命周期、PUBLIC 协助状态事件和相应前端接入。
- 新增迁移 0021，按工作区中已存在的 0020 migration 衔接；没有接触真实 Anker 服务。
- FastAPI 导出 OpenAPI 并生成前端 Client。最终回归：后端 167 passed/204 skipped；浏览器 99 passed；隔离 live API/DB 6 passed；ruff、OpenAPI drift、API type drift、typecheck、build 均通过（build 有 513.84 kB chunk advisory）。
- 实际业务约束与未实施边界见 `specs/018-interaction-contract-alignment/contracts/feature-contract.md`；验收摘要见 `docs/interaction-contract-validation.md`。
- 用户可见原则：TaskRead 之外不推断接手、无 ETA/presence；proposal/draft 不进入客户时间线，审批与发送分离，只有真实 PUBLIC MessageReceipt/消息事件代表已发送。
- 自动化验收只证明本地实现和隔离测试环境；真实 Anker、生产部署、真实 Provider 与用户手动目视签收仍未验收。详细命令和限制写入 `docs/interaction-contract-validation.md`。
