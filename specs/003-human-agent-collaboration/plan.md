# Implementation Plan: Human and Agent Collaboration

使用 PostgreSQL 行锁、乐观版本和独立 ServiceTask/Assignment 状态。ConversationService 持有公开发布边界。AgentProposal 保留内部且审阅状态可追踪；任何 ACTION 提案只可审批或拒绝，执行由阶段 4 独立实现。

## Technical Context

FastAPI、Pydantic、SQLAlchemy/Alembic、PostgreSQL 与生成的 React Client。

## Constitution Check

Case、Conversation、Task、AgentRun 独立；发言权不等于动作权；人工主导的内部工作可继续。
