# Internal Agent Result v1

Runtime 产出 `text: str`、`ui_proposal?: {purpose, audience, fallback_text, component_hints}`、`action_proposals: UUID[]`。`component_hints` 仅允许已列举的名称；此契约不发布 HTTP API，也不表示 UI 已渲染或动作已执行。非法 UI 退回文本，记录 `ui_fallback_code`；缺失文本令 Run 失败。
