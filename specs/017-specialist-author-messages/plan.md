# 实施计划：诊断专家作者消息

## 阶段 1：统一契约

- 固定作者类型、来源关联、PUBLIC/INTERNAL 矩阵、排除状态、幂等及正文投影。
- 后端持久化和 Conversation Service 是唯一业务写入边界；复用现有消息 GET、Outbox 和 `message.created` 消费路径。

## 阶段 2：数据库和应用服务

- 新增 Alembic 0019，为 `messages` 添加可空 `specialist_run_id` 与复合 tenant FK。
- 更新作者身份 CHECK：SPECIALIST 必须有关联 SpecialistRun 且不带客户/员工 actor；非 SPECIALIST 不得带 specialist_run_id。
- 增加 `(tenant_id, specialist_run_id)` 唯一约束，NULL 对非专家消息不冲突。
- 新增 `ConversationService.publish_specialist_result`，检查当前对话、父 AgentRun lease、Task/Run 归属与状态、策略和公开文本 guard；消息与 Outbox 保持在诊断完成事务内。
- `ASK_CUSTOMER` 不生成专家结果消息；SAFETY_STOP/HUMAN_REVIEW 只走既有固定安全/人工回复；已完成且可展示的结果在自动公开策略下 PUBLIC，其余活动策略 INTERNAL。

## 阶段 3：API 与前端

- `MessageRead.author_kind` 使用已知 Literal 集合并含 SPECIALIST；不向客户暴露 SpecialistRun UUID；SendMessage 不增加 attribution 写字段。
- 导出 OpenAPI 并生成 TypeScript Client。
- MessageThread 显示诊断专家身份和待核验标记；专家消息不获得 AGENT 的 RichReply/快捷回复处理。
- 更新 Agent 工具返回值/提示，让 Service Agent 知晓专家结果已经持久发布，并仅补充协调信息。

## 阶段 4：验收与文档

- 后端 PostgreSQL 测试覆盖权限策略、租户/来源 FK、幂等重放/冲突、问题/安全路径、事务回滚、失租约拒绝、客户读隔离。
- OpenAPI 导出/漂移、生成 Client 检查、前端 typecheck/build、专家消息浏览器场景。
- 更新 feature 011 现状链接、domain-and-contracts、development-plan 及独立验收记录；注明生产 Provider 验收边界。

## 主要涉及文件

- `backend/serviceos_api/persistence/models.py`
- `backend/migrations/versions/0019_specialist_author_messages.py`
- `backend/serviceos_api/application/{contracts.py,services.py,agent_services.py,diagnostic_contracts.py}`
- `backend/serviceos_api/agents/runtime.py`、必要时 `backend/serviceos_api/worker/runtime.py`
- `backend/tests/test_database.py`、诊断/Worker 测试
- `frontend/src/features/conversation/MessageThread.tsx`、`frontend/src/api/schema.d.ts`、相关浏览器用例与消息样式
- `specs/017-specialist-author-messages/`、`specs/011-visible-specialist-orchestration/contracts/feature-contract.md`、`docs/domain-and-contracts.md`、`docs/development-plan.md`
