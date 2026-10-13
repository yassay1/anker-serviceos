# Implementation Plan: 阶段 2 Agent 结果分离

**Branch**: `001-agent-result-separation` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

## Summary

保留现有 Worker、Agent 工具和公开发布边界。新增受限结构化结果解析与内部持久审计；UI 校验失败只降级 UI，文本仍走 Conversation Service。动作引用由数据库中同 Run 的内部草稿生成。

## Technical Context

**Language/Version**: Python 3.12；前端 TypeScript 5.9 仅做契约回归。  
**Primary Dependencies**: LangChain `create_agent`、Pydantic、SQLAlchemy、Alembic。  
**Storage**: PostgreSQL `serviceos` AgentRun；独立 checkpoint schema 不变。  
**Testing**: pytest + 临时 PostgreSQL 数据库。  
**Target Platform**: 独立 Worker 进程。  
**Project Type**: FastAPI 后端与 React 前端同仓。  
**Performance Goals**: 消息受理不等待模型；解析与校验在 Worker 中完成。  
**Constraints**: 无 Provider 凭据；不得将替身称为真实模型验收。  
**Scale/Scope**: 一个阶段 2 结果契约，不发布 UI API。

## Constitution Check

通过：证据与事实边界沿用 Context Builder；公开权限由 Conversation Service 复核；内部草稿不执行动作；租约与幂等沿用现有 Worker。完整 UI 文档与交互留给阶段 3，避免越权上线。

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-result-separation/{spec,clarifications,plan,research,data-model,quickstart,tasks}.md
specs/001-agent-result-separation/checklists/requirements.md
```

### Source Code (repository root)

```text
backend/serviceos_api/agents/{runtime,result}.py
backend/serviceos_api/worker/runtime.py
backend/serviceos_api/persistence/models.py
backend/migrations/versions/0005_agent_result.py
backend/tests/{test_agent_result,test_worker_runtime}.py
docs/{development-plan,phase2-validation}.md
```

**Structure Decision**: 复用现有模块与应用服务，不建第二套公开消息或动作服务。

## Complexity Tracking

无宪章例外。
