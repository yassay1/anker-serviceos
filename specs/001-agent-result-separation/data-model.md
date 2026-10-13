# Data Model

`AgentRun.result_text` 保留独立文本；新增 `result_payload` JSONB，含 `schema_version=1`、`ui_proposal`（可空）、`action_proposals`（内部草稿 ID 列表）、`ui_fallback_code`（可空）。结果在持有当前租约且 RUNNING 时写入。恢复时重新使用已保存文本与 payload。

`UIProposal` 仅含目的、目标 audience、fallback_text 与受限 component hints。它不含脚本、HTML、URL、任意 props、业务状态或执行权限。`AgentProposal` 继续作为内部草稿权威记录；结果只引用现有记录，不改变审批/执行状态。
