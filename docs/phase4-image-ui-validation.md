# 阶段 4 图片证据界面增量验收

`/cases` 对客户和客服展示所属 Case 的图片记录。客户只可提交公开图片，客服可选内部可见。上传提交含 Case 版本和客户端证据编号；断线或未知响应时保留同一编号及图片摘要，列表若返回该编号可对账。页面显示真实 `PENDING`/`CLEAN`/`REJECTED`，只在 `CLEAN` 时请求受授权的原图；预览使用短时 Blob URL 并在关闭或离开时释放。

后端 `EvidenceRead` 增加 `client_evidence_id` 投影，供前端对账。检查 Worker 增加 `--once`，便于隔离流程验收。它们不改变上传、租户隔离或存储规则。

本地验收（2026-10-14）：`uv run --project backend --locked pytest backend/tests --require-postgres -q` 为 91 通过；`python -m serviceos_api.export_openapi --check`、拟定契约同步检查、`npm run check:api`、`npm run typecheck`、`npm run build` 均通过。`npm run test:browser` 为 33 通过，`npm run test:live` 为 4 通过。真实 API 浏览器测试覆盖客户上传、待检查拒绝读取、Worker 结构检查后预览、其他客户隐藏、客服内部图片不泄漏以及移动端宽度。远端 CI 状态以对应 PR 记录为准。

范围限制：本地 `CLEAN` 是结构检查，不是病毒扫描或模型理解。生产对象存储适配器尚未配置；格式、10 MiB 和尺寸阈值仍为产品待确认提案。阶段 4 对应复选框保持未完成。
