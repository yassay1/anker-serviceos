# Implementation Plan: 售后闭环与可复现交付

**Branch**: `phase5/delivery-readiness` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)
**Input**: `specs/009-delivery-readiness/spec.md`

## Summary

基线为 main `10fe1fcd60b02c54430df0aa66af784767a3963d`。阶段四动作、客户核验、同意后回访及事实归档已经存在，本轮先回归并修补真实缺口。新增容器化交付、分层就绪检测、安全运行配置和运维脚本；以现有 AgentRun 记录扩展 Skill，明确情绪仅是辅助信号；完善实时恢复及聊天内的业务入口。

## Technical Context

**Language/Version**: Python 3.12、Node 24、TypeScript 5.9。
**Primary Dependencies**: 现有 FastAPI、SQLAlchemy、Alembic、LangChain create_agent、React、TanStack Query、Vite；不换栈。
**Storage**: PostgreSQL 17 业务与 checkpoint 独立 schema；本地私有文件卷，S3 适配器通过现有 EvidenceStorage 协议接入。
**Testing**: pytest 真实 PostgreSQL、Playwright 模拟网络测试与真实本地 API 流程、Compose 配置/构建/启动、恢复演练。
**Target Platform**: Windows 原生开发与 Linux Docker；生产方向 EC2 + RDS + 私有 S3，无实际云部署。
**Project Type**: 单仓前后端 + 独立 Worker 模块化单体。
**Performance Goals**: 记录 http_accept_ms、queue_delay_ms、真实进度、工具和操作耗时、错误率及 P50/P95；模型数据缺少时未测。
**Constraints**: 不暴露内部推理；不盲重试 UNKNOWN；不把 Mock 当真实接口；不以生产配置启用开发身份；不自动请求模型。
**Scale/Scope**: 当前本地演示及单机交付，不引入通用 Skill 商店或分布式队列。

## Constitution Check

研究前与设计后均通过：沿用独立核心对象、类型化应用服务、ConversationService 对外发布、版本/幂等/审批；新接口只有真实实现后导出。公共进度使用固定白名单摘要；情绪模型结果只作推测。现有业务测试不可绕过，真实 Provider、生产身份和云环境分别保留未通过门槛。Spec/plan/tasks 完成一致性分析后才实现。

## Project Structure

- `backend/serviceos_api/settings.py`, `api/health.py`, `api/dependencies.py`, `main.py`：安全配置、就绪响应与请求观测。
- `backend/serviceos_api/observability.py`, `operations.py`：结构化脱敏日志、受控本地演示初始化/重置/性能命令。
- `backend/serviceos_api/application/skills.py`, `api/skills.py`：版本化 Skill 契约、发现和 INTERNAL 执行记录；不复制售后规则。
- `backend/serviceos_api/agents/runtime.py`, `application/agent_services.py`, `worker/runtime.py`：受限加载、现有 run 审计、确定性进度。
- `backend/serviceos_api/application/services.py`：仅必要的公共进度白名单和已证实业务缺口修复。
- `backend/serviceos_api/integrations/`：沿用私有本地证据协议，补私有 S3 适配与拒绝路径测试。
- `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`, `compose.production.yaml`, `deploy/`：独立服务、一次性迁移、Nginx SSE/HTTPS、环境模板。
- `.github/workflows/ci.yml`：保留已有真实 PG 和 live E2E，增交付配置校验及安全检查。
- `frontend/src/features/conversation/`, `features/ui-document/`, `styles/`：卡片差异化、聊天中心、受控业务入口和事件恢复。
- `docs/operations.md`, `docs/service-sop.md`, `docs/phase5-validation.md`：运行、恢复、SOP和真实验收。

**Structure Decision**: 只在现有边界增量，不拆第二套业务系统。各并行工作明确文件所有权；生成 OpenAPI/Client 由集成负责人最后统一生成。

## Implementation sequence

1. 跑最新 main 的真实 PG、前端和 live 测试，核对阶段四缺口。
2. 并行推进交付文件、运行时 Skill/进度、前端体验；主任务负责 Settings/health/日志/存储/集成。
3. 开发 Compose 将 API/非模型 Worker 与 PG17 持久卷串联，Agent 以显式 profile 启用；生产使用外部数据库、TLS和私有对象存储，身份未接入则阻止业务开放。
4. 就绪区分 DB/schema、auth、storage、provider 配置；健康请求不调用模型。开发容器只允许显式私有网络且网关仅绑定回环，生产永不允许开发登录。
5. Skill 在固定注册表中声明 metadata/input/output/UI hints，加载只记 LOADED；情绪契约为 PREPARED，未接模型不产生已识别结果。
6. 进度由 Worker/工具入口写固定枚举，Outbox 交给 ConversationService；前端校验序号并重新查询权威状态，不用内部 sequence 空洞推断漏事件。
7. 统一导出契约、全套回归、真实浏览器桌面/移动端、容器重启/恢复演练，更新验收记录与阶段勾选。

## Complexity Tracking

无宪章例外。生产身份源与真实模型凭据是外部前置条件，不添加临时认证绕过或测试替身冒充生产能力。
