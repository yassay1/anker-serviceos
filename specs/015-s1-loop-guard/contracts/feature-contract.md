# S1 闭环核：政策注册表 + 结局 taxonomy + 发布守卫（含前端可视化）· 功能契约

状态：草案 v1，经 2026-10-17 用户确认调整实时发布门禁范围。
原双检查设计保留为评测目标；实时发布不再调用 LLM 覆盖/承诺 verifier。

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 切片 | specs/015-s1-loop-guard |
| 用户目标 | 客户：答复有凭据、请求不漏；客服：/desk 看到被拦草稿+原因+证据，可复核发布；主管：政策命中与结局分布可见 |
| 涉及对象 | 新表 `service_policies`、`publication_guard_decisions`；`case_actions.remedy_type`；AgentProposal(REPLY) 复用为被拦草稿载体 |
| 负责人 | 同一人 |

## 2. 政策注册表（DMN 式）

- 表 `serviceos.service_policies`：id、country('*')、channel(DIRECT/AUTHORIZED_DEALER/UNAUTHORIZED/'*')、product_family(ROBOVAC/BREAST_PUMP/'*')、warranty_state(IN/OUT/UNKNOWN)、remedies JSONB{allowed[],wording_ref}、rule_id、version、effective_from/to、status(ACTIVE/SUPERSEDED)、source_ref
- 命中策略=优先级：精确 country > '*'；精确 channel > '*'；精确 family > '*'；同分取 version 新
- 种子 `policies-v1.jsonl`（赛题规则 curated，标注参考）：保内+授权→[REPAIR,RESHIP]；保外→[DECLINE]+告知口径；非授权→[REFER_SELLER]；UNKNOWN→[REPAIR]+先核验
- 工具 `resolve_policy(country, channel, product_family, warranty_state)`：信封带命中 rule_id+version（reason code）；NOT_FOUND 类型化
- 每条规则行配决策表测试用例进 CI

## 3. 结局 taxonomy

- `MockActionRequest.remedy_type ∈ {REPAIR, RESHIP, REFER_SELLER, DECLINE}`（必填）；回执与 CaseActionRead 携带；审批照旧
- Case 结局投影 = 最新核验通过动作之 remedy_type；/desk 案例详情显示结局徽章

## 4. 发布守卫（PublicationGuard）

- 挂点：`ConversationService.publish_agent_response` 判定 PUBLIC 之前；仅对将公开的 Agent 文本运行
- 实时检查：确定性抽取型号、日期、带单位数值和 4 位错误码，并对比客户原话及授权证据束；未命中=`UNGROUNDED_ENTITY`。该检查不替代 Case、Device 或外部动作的应用服务授权与状态校验。
- LLM 覆盖/承诺判断不在实时发布路径运行，不产生 `UNCOVERED_REQUEST` 或 `VERIFIER_UNAVAILABLE` 发布阻断。该类语义质量由离线多轮评测观察，必须分别报告合法回复误拦、风险漏拦和任务完成情况。
- 拦截→不发布：原 reply 转 INTERNAL 草稿 + AgentProposal(REPLY) + `publication_guard_decisions` 行（run_id、message refs、确定性 entities、decision、latency_ms）。本项目不自动生成客户兜底消息；被拦回复由客服/主管按现有人工流程处理。
- override：SUPERVISOR/ADMIN 经 `POST /api/v1/guard/decisions/{id}/override` 发布（maker-checker：override 者≠run 发起人无需强制但审计留痕）；发布后决策行带 override ref
- 开关 `SERVICEOS_PUBLICATION_GUARD`（默认 on）；readiness `guard=on/off`；CI 断言 off 需显式
- references 扩存 excerpt（INTERNAL only）供接地比对

## 5. HTTP 操作（新增）

- `GET /api/v1/policies`（staff）：规则列表含 status/version
- `GET /api/v1/guard/decisions`（staff，cursor）：决策流（含 reason codes、被拦草稿 id）
- `GET /api/v1/guard/decisions/{id}`：明细（entities、verdict、verifier 摘要、override）
- `POST /api/v1/guard/decisions/{id}/override`（SUPERVISOR/ADMIN）：发布被拦草稿
- `GET /api/v1/guard/stats`：blocked/overridden/passed 计数（面板用）
- 错误语义：401/403/404/409（已 override/已发布重复 override）

## 6. 前端可视化（/desk）

- 新增"发布守卫"面板：决策流列表（时间/会话/原因徽章/状态），点开明细：被拦 reply 全文、未接地实体清单（含证据束比对结果）、实时语义检查状态；SUPERVISOR/ADMIN 见"复核发布"按钮（二次确认）
- 案例详情：结局徽章（REPAIR/RESHIP/REFER_SELLER/DECLINE）+ 政策命中行（rule_id@version + wording_ref）
- 会话侧栏：本 run 的 knowledge_references 可视化（来源/路径 keyword|vector|fused）
- 守卫统计条：passed/blocked/overridden（来自 /guard/stats）
- 全部只读真实服务器数据；无假进度

## 7. 验收

| 路径 | 预期 |
|---|---|
| 注入无据型号 T9999 | 拦截→决策行 UNGROUNDED_ENTITY→/desk 可见→override 发布+审计 |
| 流程性安全表述（无型号/日期/数值/错误码等未依据实体） | 不因语义 verifier 拦截；该轮对话体验进入离线人工/数据集评测 |
| 有无依据的型号、日期、单位数值或错误码 | 确定性实体证据检查分别放行/拦截，拦截原因 `UNGROUNDED_ENTITY` |
| Provider/verifier 宕机 | 实时发布守卫不调用语义 verifier，不影响该检查；Agent 生成/业务 API 的自身失败策略仍适用 |
| guard=off | readiness guard=off 且 CI 断言 |
| SOP 五分支回放 | remedy_type 与政策命中一致；回执带结局 |
| 决策表测试 | 每条 policy 行输入→命中 rule_id 断言 |
| 前端 | 面板/徽章/引用可视化 typecheck+build+live 浏览器路径 |
| 回归 | 实时发布不发起 verifier Provider 请求；有依据实体通过、无依据实体仍拦截；守卫拒绝时不生成客户兜底 |

## 8. 明确不包含

原子声明级接地（v2）、span 级客户引用渲染、政策可视化编辑、多意图 subgoals、情绪策略（S3）、CSAT（S2）。

## 9. 落地记录

- 实现后回填。
