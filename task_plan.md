# 任务计划：诊断专家独立作者消息

## 目标
先核实当前实现并形成可确认的跨模块实施计划；用户确认后，将经过授权的诊断结果作为带持久专家来源的独立作者消息呈现在会话中。

## 当前状态
实现和本地自动化验收已完成；交付记录见 [progress.md](progress.md) 和 [specialist-author-messages-validation.md](docs/specialist-author-messages-validation.md)。

## 阶段状态

## 各阶段
### 阶段 1：需求与现状核对
- [x] 阅读 V1 基线、模块 README、baseline-integration 和 contributing。
- [x] 核对消息模型、发布权限、诊断完成、API、SSE 与前端作者渲染。
- **状态：** complete

### 阶段 2：形成可审阅实施计划
- [x] 明确需要新增的模型、事务、发布策略和前端行为。
- [x] 列出契约决策、实现次序、验收命令与风险。
- **状态：** complete

### 阶段 3：契约与方案确认
- [x] 用户确认按计划执行：公开策略发布 PUBLIC，其他模式保存 INTERNAL；保留主 Agent 回复并避免复述。
- **状态：** complete

### 阶段 4：实现与验收
- [x] 更新功能契约与领域文档。
- [x] 实现持久化、Conversation Service 发布、API/OpenAPI、前端作者展示。
- [x] 增加测试并执行后端、迁移、契约与前端验收。
- **状态：** complete

## 最终状态
- 功能代码与本地自动化验收完成；真实 Provider 行为与生产环境验收不在本轮验证范围。

## 已确认的现状
- 诊断活动卡和 `specialist.activity` 已实现；现有契约明确它不是聊天 Message。
- `Message` 当前没有 SPECIALIST 作者类型或 SpecialistRun 来源 FK；消息 API 由服务端生成作者身份。
- `complete_diagnostic` 验证并提交结果/活动事件；ConversationService 的 `publish_agent_response` 是公开回复授权控制点。
- 诊断结构验证绑定 task/evidence refs，但不等同于完整公开内容安全检查；当前公开活动只投影受限 assessment 摘要。
- 协作模式由后端控制；服务端消息历史对客户过滤 INTERNAL，SSE 同样有可见性过滤。
- feature 011 的 A-D 代码已实现，但其当前契约明确专家结果不是消息作者身份。宜新增独立功能切片/契约，而不是把已交付行为追溯改写。

## 已确认的实现决策
- 新增 `SPECIALIST` 作者身份，并以 tenant-scoped `specialist_run_id` 关联来源；普通 SendMessage 不接受作者类型、显示名或 run id。
- 一条 SpecialistRun 最多关联一条专家结果消息；消息和 `message.created` outbox 在诊断完成事务中原子提交。
- 只在会话 ACTIVE、`AI_LEAD + AI_AUTO` 且通过现有公开内容安全门时发布 PUBLIC 专家消息；追问、安全停止、人工复核不生成专家自由文本消息。
- CO_SERVICE / AI_REVIEW_REQUIRED / HUMAN_LEAD 下把合格结果保存为 INTERNAL SPECIALIST 消息供客服审阅，不自动公开；不制造未经确认的人工审批流程。
- 保留主 Agent 的协调职责；后续回复提示读取专家结果并避免重复结论，问题卡已提问时不再重复询问。

## 验收轮廓
- PostgreSQL 成功/拒绝/租户隔离/每 run 幂等/事务回滚测试。
- API 契约断言读消息暴露 SPECIALIST 作者标识，但写消息不能伪造身份；OpenAPI 导出/漂移和生成 Client 同步。
- AI_LEAD+AI_AUTO 可看到唯一、标记为待核验假设的专家消息；CO_SERVICE/HUMAN_LEAD、失效会话、策略变更、安全与追问路径不公开专家正文。
- 前端历史与 `message.created` SSE 渲染“诊断专家 / AI 假设”；不赋予 Agent 快捷回复行为。
- 执行后端定向及完整测试、OpenAPI 检查、前端 Client 检查/typecheck/build 与相关浏览器路径。

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|---|---:|---|
| `init-session.ps1` 在未绑定 PLAN_ID 时把模板写入仓库根目录 | 1 | 将根目录模板整理为本任务计划；未触碰既有 `.planning/visible-specialist-orchestration` 计划 |
