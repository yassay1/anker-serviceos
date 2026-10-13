# Implementation Plan: Controlled UI Documents and Intents

新增 UIDocument 与 UIActionInvocation 表。Conversation Service 生成可恢复快照并持久化 revision 与事件；Catalog Validator 验证受信组件、数据来源、动作和资源关联。前端仅根据版本化目录渲染受信类型，未知类型退回 fallback。动作由应用服务统一执行请求人工任务命令。

## Technical Context

Python 3.12、Pydantic、SQLAlchemy/Alembic、FastAPI；React/TypeScript。生成 OpenAPI/Client 与后端同源。

## Constitution Check

UI 是投影且不提供执行权限；业务写入仍由应用服务完成。公开投影与事件经 Conversation Service；Agent 提案先校验且不得直接成为客户事实。
