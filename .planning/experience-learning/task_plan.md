# ServiceOS 售后经验沉淀与复用计划

## 目标
基于已核验 Case 建立可追溯、经人工审核、按授权范围检索的经验闭环；不让经验自动升级为 VERIFIED 事实或自动改写线上 Skill/SOP。

## 下一步
实现主体已完成。若要关闭 PostgreSQL 验收剩余项，需要启动项目支持的本机 PostgreSQL 并运行 `--require-postgres` 目标测试及迁移验证。

## 当前阶段
阶段 5：文档和最终验收（PostgreSQL 集成验证受本机服务不可用限制）

## 各阶段
### 阶段 1：契约与实现边界
- [x] 核对项目基线、真实实现及现有工作区状态
- [x] 确认经验记录字段、状态流转、触发时机、审核权限和复用范围
- [x] 记录字段/接口契约和验收方案
- **状态：** complete

### 阶段 2：持久化候选经验
- [x] 增加租户隔离的 ExperienceCandidate、ExperienceReview 表与 Alembic 迁移
- [x] 仅从 `VERIFIED_RESOLVED` 核验生成不含客户文本的待整理候选；保证幂等
- [x] 候选整理不增加用户对话路径模型调用
- **状态：** complete（迁移离线生成通过；数据库升级/降级待 PostgreSQL 环境复验）

### 阶段 3：客服审核与状态审计
- [x] 实现同租户客服读取和审核接口
- [x] 支持批准、拒绝、修订；使用版本锁和唯一操作键
- [x] 审核通过仅使候选经验可检索，不改变 DeviceFact 或 Skill 权限
- **状态：** complete

### 阶段 4：运行时按需复用
- [x] Context Builder 检索少量已批准、适用型号/类别的经验
- [x] 明确标记为参考案例并携带来源，不作为事实或操作授权
- [x] 先使用 PostgreSQL 结构筛选/关键词匹配，不引入向量库
- **状态：** complete（真实 JSONB 查询待 PostgreSQL 验收）

### 阶段 5：验证与文档
- [x] 补充租户/权限/状态转换/去重/检索边界集成测试
- [x] 运行直接相关测试、OpenAPI 校验、前端契约检查和离线迁移 SQL 生成
- [x] 更新开发计划、SOP、阶段验收说明与 OpenAPI/生成类型
- [ ] 在真实本地 PostgreSQL 上运行集成测试及迁移升级/降级
- **状态：** in_progress（本机 PostgreSQL/Docker 不可用，详见验收记录）

## 验收标准
- 未解决、未经核验的 Case 不能成为批准经验。
- 每条经验都保留租户、Case/Evidence/Action/Verification 来源和审核者。
- 客户不能读取或审核经验；客服只能访问自身租户数据。
- 重复事件/重试不会创建多条等价候选或重复审核副作用。
- Agent 只收到少量相关批准经验；经验不能覆盖当前事实、扩权或触发业务动作。
- 保持现有 Agent Loop、API 兼容和不增加每轮摘要调用。

## 决策
| 决策 | 理由 |
|---|---|
| 仅在正式 `VERIFIED_RESOLVED` 后同步创建空白待整理候选，不使用 LLM 总结 | 避免每轮/每案额外模型调用；不复制客户文本，避免敏感信息沉淀 |
| Approved 经验先作为案例参考，不动态改写 Skill/SOP | 避免把局部案例误提升为通用流程；Skill 继续代码版本发布 |
| 首版仅按已核验型号和人工标注的问题关键词检索同租户 Approved 经验 | 复用现有 PostgreSQL 与手册检索思路；未核验型号时不把案例作为设备适用建议 |
| 使用独立内部经验审核 API，不复用 PUBLIC/INTERNAL SSE 事件作为工作队列 | 避免内部复盘内容被会话事件通道误发布 |

## 遇到的错误
| 错误 | 次数 | 解决方案 |
|---|---:|---|
| 根目录 task_plan.md/findings.md/progress.md 是先前集成任务的未跟踪文件 | 1 | 保持原样，在 `.planning/experience-learning/` 建立本任务独立规划 |
| 指定的 `backend/tests/test_verification.py` 不存在 | 1 | 按现有测试目录实际文件调整为 `test_mock_service_actions.py`、`test_business_api.py` 和相关测试 |
