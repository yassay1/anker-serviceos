# Tasks: 售后闭环与可复现交付

**Input**: `specs/009-delivery-readiness/` spec/plan/research/data-model/contracts/quickstart。
**Tests**: 用户明确要求成功、异常及真实 PostgreSQL/浏览器验收。勾选仅在实际执行后更新。

## Phase 1: Setup

- [x] T001 核对 main 10fe1fc 和既有验收，在 docs/phase5-validation.md 记录基线及环境限制。
- [x] T002 完成 specs/009-delivery-readiness/ 的规格、设计、契约、任务一致性审查。

## Phase 2: Foundational

- [x] T003 运行 backend/tests 和 frontend/tests 的基线回归，记录实际失败而非绕过。
- [x] T004 确认 specs/009-delivery-readiness/contracts/feature-contract.md 的共享设置、事件、接口和文件所有权。

## Phase 3: User Story 1 - 可重复启动与恢复 (P1)

Goal: 安全、可重复启动及恢复；独立验收为容器初始化、重启与恢复测试。

- [x] T005 [P] [US1] 在 backend/tests/test_readiness.py 覆盖 DB/schema不符、认证禁用、生产local拒绝、来源及秘密不泄漏。
- [x] T006 [US1] 在 backend/serviceos_api/settings.py、api/dependencies.py、api/health.py、main.py 实现配置隔离、显式本地容器网络与分层就绪。
- [x] T007 [P] [US1] 在 backend/serviceos_api/observability.py 和 backend/tests/test_observability.py 实现有界结构化脱敏日志、请求关联与耗时。
- [x] T008 [P] [US1] 在 backend/Dockerfile、frontend/Dockerfile、compose.yaml、compose.production.yaml、deploy/ 实现独立API/Workers、一次性迁移、持久卷和Nginx SSE/HTTPS。
- [x] T009 [P] [US1] 在 backend/serviceos_api/integrations/s3_evidence_storage.py 和 backend/tests/test_evidence_storage.py 实现私有S3协议、限定对象键、有界读取及异常测试，生产禁止本地回退。
- [x] T010 [US1] 在 backend/serviceos_api/operations.py、backend/tests/test_operations.py 实现受控演示seed/reset和性能采集；reset仅允许显式隔离演示目标且要求确认。
- [x] T011 [US1] 在 docs/operations.md 完成开发/生产依赖、迁移、备份、恢复、回滚、EC2/RDS/S3网络及身份阻断说明。
- [ ] T012 [US1] 按 docs/operations.md 完成本地容器构建、初始化、重启和隔离备份恢复演练并记录证据。**未完成**：本网络到 Docker Hub / PyPI 无法在合理时间内拉齐依赖（单包 15MB 下载超过 25 分钟仍未完成），前端镜像已建成、三个 compose 配置可独立校验；完整演练由 CI 的 container-smoke 作业执行，本项不勾选。

## Phase 4: User Story 2 - 连续、受控的售后服务 (P1)

Goal: 复用现有动作/核验/跟进/事实服务，闭环不越权；独立验收为真实PG与浏览器链路。

- [x] T013 [P] [US2] 审查并在 backend/tests/test_mock_service_actions.py、test_followups.py、test_case_fact_archive.py 补真实已证实的失败/并发/解决门槛回归。
- [x] T014 [US2] 在 backend/serviceos_api/application/ 对已证实闭环缺口做最小修复，禁止重复建设既有服务。
- [x] T015 [P] [US2] 在 docs/service-sop.md 编写逐阶段信息要求、追问/工具/UI触发、状态门槛、人工升级及异常矩阵。
- [x] T016 [US2] 在 frontend/tests-live/service-flow.spec.ts 完成真实客户/客服/主管、图片、动作、UNKNOWN、核验、回访和事实归档流程回归。（本机 6 passed，独立数据库 serviceos_dev）

## Phase 5: User Story 3 - 界面及实时一致 (P1)

Goal: 聊天与当前任务清晰、客服资料可达；独立验收为桌面/移动端及断线恢复。

- [x] T017 [P] [US3] 在 backend/tests/test_worker_runtime.py 和 frontend/tests/ 增进度发布、内部隔离、重复/乱序事件、失效卡片回归。（后端与浏览器两侧均通过）
- [x] T018 [US3] 在 backend/serviceos_api/worker/runtime.py、application/agent_services.py、application/services.py 增实际执行的固定枚举进度，经ConversationService发布，禁止推理/工具参数外泄。
- [x] T019 [P] [US3] 在 frontend/src/features/conversation/useConversationEvents.ts 实现单调游标、去重、重连快照及可用状态恢复，不能将合法内部序号空洞当漏事件。（delivery-readiness 浏览器用例通过）
- [x] T020 [US3] 在 frontend/src/features/conversation/ConversationWorkspace.tsx、features/ui-document/UIDocumentRenderer.tsx、styles/ 改善聊天中心、关联Case/下一步入口、差异化卡片和移动端状态。（typecheck/build 通过，桌面与手机浏览器用例通过）
- [x] T021 [US3] 在 frontend/tests/ 验证加载/空态/失败/权限/网络状态，真实浏览器复查桌面和移动端并保存本地验收证据。（60 passed，含 axe 安全检查与截图产物）

## Phase 6: User Story 4 - Skill可扩展 (P2)

Goal: 方法、工具和授权边界清晰，情绪仅为辅助；独立验收为契约/租约/可见性测试。

- [x] T022 [P] [US4] 在 backend/tests/test_skills.py 编写Skill未知版本、PREPARED不可执行、租约、来源、内部可见和情绪策略越权拒绝测试。
- [x] T023 [US4] 在 backend/serviceos_api/application/skills.py 定义固定元数据、版本、input/output Schema和availability；情绪intensity/confidence均为[0,1]，保留uncertainty和授权消息依据。
- [x] T024 [US4] 在 backend/serviceos_api/agents/runtime.py、application/agent_services.py、worker/runtime.py 接受限Skill加载及run结果审计；LOADED不等于COMPLETED，同一run/key幂等。
- [x] T025 [US4] 在 backend/serviceos_api/api/skills.py 实现同租户客服的目录与有界分页INTERNAL执行记录，客户403/跨租户404，并在main.py注册。

## Phase 7: Integration and evidence

- [x] T026 同步 contracts/openapi.json、contracts/proposed/v1/ 和 frontend/src/api/schema.d.ts；运行生成漂移检查。
- [x] T027 在 .github/workflows/ci.yml 保留PG与live E2E，增加部署配置和依赖安全检查，实际远端CI不冒充本地结果。
- [x] T028 运行全套后端、前端、迁移和关键异常回归，按 docs/phase5-validation.md 记录命令、样本数、P50/P95、结果和未测项。（后端 168 passed、浏览器 60 passed、真实端到端 6 passed、迁移 0001→0013、`http_request_ms` 992 样本 P50 12.29/P95 33.89 ms；未测项已单列）
- [x] T029 更新 README.md、backend/README.md、frontend/README.md、docs/development-plan.md 和 docs/baseline-integration.md，仅勾选已验证范围。（已更新根 README、后端 README、开发计划；前端 README 与合并归档说明本轮无需改动）
- [x] T030 本地保留可访问体验服务，在 docs/phase5-validation.md 明示Provider、生产认证、云存储/HTTPS和真实Anker接口各自未验收门槛。

## Dependencies & Parallel execution

T001–T004完成后：US1交付文件(T008/T011/T027)、主任务配置健康存储(T005–T010)、US3/US4运行时(T017/T018/T022–T025)和前端(T019–T021)分文件并行；T014由审查结论驱动。生产配置依赖T006；T012依赖T008/T011。T020最终接线依赖真实后端契约。T026统一执行后再T016/T021/T028，最后T029/T030。

同一services.py如涉及不同工作面，由集成负责人串行协调；生成文件不交给多个任务同时写。任何新发现的阻断问题先更新契约/任务。

## Implementation strategy

先让US1安全可运行；保留并回归US2；US3/US4补真实链路，不扩充通用平台。每个步骤都有可独立检验的结果，未通过不勾选，不因阶段五推进而默认阶段二至四完成。
