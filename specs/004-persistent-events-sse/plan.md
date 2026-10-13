# Implementation Plan: Persistent Events and SSE

沿用现有 OutboxEvent、ConversationEvent 与 Worker Dispatcher。把投递和可见性读取封装在 Conversation Service，新增持久历史与 SSE API；前端使用 event ID 补取并刷新权威消息列表。

## Technical Context

FastAPI StreamingResponse、PostgreSQL、React EventSource。无迁移。

## Constitution Check

PUBLIC 内容经 Conversation Service 最新权限与可见性检查；SSE 不持有或控制 Agent 运行。
