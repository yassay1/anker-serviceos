# Case 经验沉淀与复用 · 实施与验收记录

日期：2026-10-15。范围是同租户、人工整理和审核的售后案例经验；本记录与当前 FastAPI、PostgreSQL 和 AgentContextBuilder 实现一致。

## 已实现

- `VERIFIED_RESOLVED` 核验在其业务事务内创建唯一、空内容的 `ExperienceCandidate`，不复制客户原文、不调用 LLM。
- `ExperienceCandidate` 与 append-only `ExperienceReview` 有租户复合外键、来源 Case/Verification、状态及版本约束。迁移为 `0014_experience_candidates`，历史回填仅产生空候选。
- 同租户客服可以读取、撰写和提交候选；只有主管/管理员可以审核或撤销；整理人不能自审。版本号、审核 `decision_id` 和 request hash 保护并发及重放。
- 只有源 Case 仍为 RESOLVED/CLOSED 且来源核验仍是最新核验时才可提交/审核。运行时只检索同租户、已核验型号匹配、关键词相关的 APPROVED 候选，最多两条；已重开、撤销、型号未知或来源过期时不注入。
- Agent 收到的经验明确为非权威参考；它不会更新 `DeviceFact`、Skill/SOP 或业务权限。审核 API 是客服内部 API，未开发客服审核 UI。
- OpenAPI 从真实路由导出，前端生成类型同步。

## 验证记录

| 检查 | 命令/结果 |
|---|---|
| Python 编译 | `uv run --project backend --locked python -m compileall -q backend/serviceos_api backend/tests`：通过 |
| 目标测试与路由基线 | `uv run --project backend --locked pytest backend/tests/test_experience_learning.py backend/tests/test_agent_context_helpers.py backend/tests/test_skills.py backend/tests/test_api_baseline.py -q`：23 passed, 14 skipped |
| OpenAPI 路由漂移 | `uv run --project backend --locked python -m serviceos_api.export_openapi --check`：matches actual application |
| 前端类型同步 | `npm run generate:api`、`npm run check:api`：API types match OpenAPI |
| 迁移离线生成 | `alembic upgrade head --sql`：成功生成 SQL；不是实际 PostgreSQL 升级/降级验证 |

14 个 skipped 中包含依赖 `SERVICEOS_TEST_DATABASE_URL` 的 PostgreSQL 集成测试。此环境的 `127.0.0.1:55432` 和 `:5432` 均无监听，本机 Docker 引擎不可用，也没有本地 PostgreSQL 可执行文件。因此候选事务、复合外键、API 租户隔离、审核状态转换、真实 JSONB 检索与迁移升级/降级尚未在 PostgreSQL 上执行验证；不要将其描述为 PostgreSQL 测试通过。恢复本地测试数据库后，按 `backend/README.md` 的 `--require-postgres` 命令运行新测试与迁移验收。

## 未实现与风险

- 没有自动抽取/总结、异步学习 Worker、向量库、跨租户共享或 Skill/SOP 自动发布；人工审核 API 暂无页面。
- 型号精确匹配加本地关键词匹配是低成本首版，召回率尚无离线案例集评估；候选数量超过近期查询窗口时可能漏召回。应先积累经审核的案例和评测，再决定是否升级检索方案。
- 未配置真实模型 Provider；Approved 经验对 Agent 的实际回答影响尚未做真实模型回归。
