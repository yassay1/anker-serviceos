# Tasks: 阶段 2 Agent 结果分离

**Input**: [spec.md](spec.md), [plan.md](plan.md), research/data-model/contracts  
**Tests**: 用户明确要求 PostgreSQL 的成功、权限、失败和恢复测试。

## Phase 1: Contract and persistence

- [x] T001 [US1] 在 `backend/tests/test_agent_result.py` 写文本/UI 分离和降级测试（FR-001/003）。
- [x] T002 [US1] 在 `backend/serviceos_api/agents/result.py` 实现有界结果解析与 UI 提案校验（FR-001/003）。
- [x] T003 [US3] 在 `backend/serviceos_api/persistence/models.py` 与 `backend/migrations/versions/0005_agent_result.py` 持久化分离结果（FR-005）。

## Phase 2: Worker integration

- [x] T004 [US3] 在 `backend/tests/test_worker_runtime.py` 增加动作引用、租约恢复、权限变化和失败测试（FR-002/004/005）。
- [x] T005 [US1] 在 `backend/serviceos_api/agents/runtime.py` 返回结构化结果；普通文本兼容（FR-001/003）。
- [x] T006 [US3] 在 `backend/serviceos_api/worker/runtime.py` 持久结果、引用同 Run 内部草稿并复用恢复结果（FR-002/004/005）。

## Phase 3: Verification and documentation

- [x] T007 [US1] 运行 PostgreSQL 测试、迁移检查、OpenAPI 和前端生成类型检查（FR-006）。
- [x] T008 [US1] 更新 `docs/development-plan.md`、`docs/phase2-validation.md`、README 的真实状态与待验项（FR-006）。

## Dependencies & Execution Order

T001→T002；T003→T004→T005→T006；T007→T008。阶段 3 的 UI 发布与 action intent 不在本切片。

