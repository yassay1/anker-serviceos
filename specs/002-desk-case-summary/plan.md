# Implementation Plan: Desk Case Summary

## Summary

复用 BusinessService 的租户与资源授权，查询 CaseConversation、CaseEvidence、CaseDevice、DevicePassport、DeviceFact，形成严格只读的客服摘要。发布真实 API 后更新生成 Client 与 /desk。

## Technical Context

Python 3.12、FastAPI、SQLAlchemy、PostgreSQL；React/TypeScript。无迁移。沿用现有 Case/Conversation 多对多关系。

## Constitution Check

证据先于判断：每项显示来源与 validity；不把候选事实写成 VERIFIED。摘要仅客服可读，不进入 PUBLIC 消息或流。

## Project Structure

修改 `backend/serviceos_api/application/{contracts,services}.py`、`api/business.py`、`frontend/src/{api/client.ts,App.tsx,styles.css}`、集成测试与生成契约。
