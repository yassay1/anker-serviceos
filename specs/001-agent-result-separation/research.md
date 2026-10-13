# Research

- 现有 `AgentRuntime.invoke` 只返回 `(text, stats)`，Worker 仅保存 `result_text`；内部动作草稿在 `agent_proposals`，已有同 Run 幂等键。
- 使用有界 JSON 对象表示模型的文本和可选 UI 元数据；普通文本仍可解析为纯文本结果。动作引用由受控工具留下的数据库草稿确定，不信任模型最终输出中的动作列表。
- 只持久化内部 UI 元数据，不创建 UIDocument 或对客 UI 事件；失败用稳定原因码而非原始模型内容审计。
- PostgreSQL Checkpointer 继续负责模型图恢复，AgentRun 负责业务持久结果，两者不能互相替代。
