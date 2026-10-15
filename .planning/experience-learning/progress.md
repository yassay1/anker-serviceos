# 进度

## 2026-10-15
- 已阅读 planning-with-files-zh 技能说明；发现仓库根目录存在其他任务的未跟踪规划文件，已保留并为本任务建独立 `.planning/experience-learning/`。
- 已核对 `AGENTS.md` 约束、README、backend/README、docs/contributing、V1 产品/架构/领域契约/开发计划/baseline-integration/SOP，以及 Case 核验、Evidence、Outbox、Worker、AgentContextBuilder 和 Skill 实现。
- 用户要求先给计划，再按阶段持续实施。阶段计划已写入 `task_plan.md`；尚未开始业务代码修改。
- 当前工作区代码状态初始干净（main 与 origin/main 同步）；仅根目录已有三份不相关未跟踪规划文件，保持原样。

### 实施进度
- 阶段 2：已新增 `0014_experience_candidates` 与租户隔离候选/审核模型；仅正式解决核验创建空候选，同一验证事务提交，无 LLM 调用。迁移回填只保存来源，不复制用户文本。
- 阶段 3：客服 API 支持有版本的撰写/提交，主管/管理员独立审核/拒绝/撤销；带决策审计和幂等键。客户不能调用，资源查询按 tenant 隔离。
- 阶段 4：Context Builder 仅注入两条同租户、已批准、已核验型号精确匹配、关键词相关且来源 Case 仍有效的参考。新增来源“最新核验”校验，防止旧经验在重开再解决后复活。
- 阶段 5：更新契约、开发计划、SOP、后端说明和独立验收记录；已导出 OpenAPI 并生成前端 API 类型。
- 最后一轮复核补充 Approved 示例的来源核验 ID/候选版本，并在相同相关度时优先较新案例；新增重开后再次解决时旧经验仍不应复活的 PostgreSQL 集成用例。
- 测试环境限制：Docker API 不可用；`127.0.0.1:55432` 和 `:5432` 不监听；没有 `postgres`/`pg_ctl`/`psql`。未尝试对开发库或生产库连接。

### 测试结果
| 检查 | 结果 |
|---|---|
| 初始 git status/diff | 代码干净；保留现有无关 untracked planning files |
| 定向测试与 API 基线 | `uv run --project backend --locked pytest backend/tests/test_experience_learning.py backend/tests/test_agent_context_helpers.py backend/tests/test_skills.py backend/tests/test_api_baseline.py -q` → 23 passed, 14 skipped (PostgreSQL) |
| Python 编译 | `uv run --project backend --locked python -m compileall -q backend/serviceos_api backend/tests` → passed |
| OpenAPI 导出检查 | `uv run --project backend --locked python -m serviceos_api.export_openapi --check` → matches actual application |
| 前端 API 类型 | `npm run generate:api`; `npm run check:api` → API types match OpenAPI |
| 迁移生成 | Alembic offline `upgrade head --sql` → succeeded; online migration and downgrade not run |
