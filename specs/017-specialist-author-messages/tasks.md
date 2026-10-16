# 实施任务

- [x] T001 确认用户批准范围并新增独立需求/计划/契约文档。
- [x] T002 扩展 Message ORM 和 0019 migration：作者来源 FK、作者身份约束、每 run 唯一。
- [x] T003 新增受控 `ConversationService.publish_specialist_result` 并与 `complete_diagnostic` 同事务调用。
- [x] T004 给结果生成安全的公开投影，区分普通完成、追问、安全停止和人工复核。
- [x] T005 更新 MessageRead/OpenAPI/生成 Client；确认普通 SendMessage 不可提供作者信息。
- [x] T006 更新 MessageThread 的 SPECIALIST 渲染和快捷回复 gating。
- [x] T007 更新 Service Agent 结果提示/状态，避免重复专家结论。
- [x] T008 新增成功、策略隔离、幂等、事务/lease、数据库约束和 API 测试。
- [x] T009 运行后端与前端验收，修复回归。
- [x] T010 更新领域/功能/开发计划文档和验收记录。
