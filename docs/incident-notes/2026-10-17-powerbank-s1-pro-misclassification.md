# 事件排查：充电宝报险被引向 S1 Pro

日期：2026-10-17（Asia/Shanghai）
范围：隔离工作区复现、定位与后端修复；不代表已部署到生产。

## 用户报告

用户输入为“我的充电宝炸了”。助手回复要求在两个产品间确认：eufy 扫地机器人 S1 Pro（T2080）或穿戴式加热吸奶器 S1 Pro（T8D04）。输入中没有产品型号或品牌限定。事故记录需优先关注爆裂/电池安全，而不是让用户在无关产品中选型。

## 复现结果

修复前，在隔离 worktree `D:\codex_worktrees\powerbank-incident-repro\Anker SreviceOS` 运行原有检索回归：

```powershell
$env:SERVICEOS_TEST_DATABASE_URL='postgresql+psycopg://serviceos_local:serviceos_local_only@127.0.0.1:55432/serviceos_dev'
uv run --project backend --locked pytest backend/tests/test_knowledge_retrieval.py -q --require-postgres
```

结果：`16 passed in 9.33s`。其中 `test_lookup_manual_returns_disambiguation_conflict_without_verified_model` 直接验证：当工具查询是 `S1 Pro 吸力变小是不是电池不行` 且无已核验型号时，`lookup_manual` 返回 `DISAMBIGUATION_REQUIRED` 和两项 S1 Pro 候选。这复现了错误回复的后半段（产品歧义列表）。

对原始用户文本直接运行 `detect_ambiguity("我的充电宝炸了", set())`，候选为空；对含 `S1 Pro` 的工具查询运行时，候选为 T2080 与 T8D04。未配置 Provider 时，`QueryRewriter` 原样保留输入文本。故“充电宝炸了”本身不会触发 S1 Pro 冲突；要出现该回复，工具查询或其他 Agent 上下文必须先带入 S1 Pro，或者模型直接生成了这段产品列表。

## 当前代码路径与定位

1. `backend/serviceos_api/agents/runtime.py:125` 将 `lookup_manual(query)` 暴露为 Agent 工具；`query` 是模型提供的参数，没有代码将客户原文强制作为唯一查询。
2. `backend/serviceos_api/application/agent_services.py:649` 在知识查询前执行 `detect_ambiguity(query, verified_models)`。
3. `backend/serviceos_api/application/knowledge_retrieval.py:27` 将 S1 Pro 固定映射为 T2080/T8D04；检测条件是查询包含字面 `s1 pro` 且没有两个候选的已核验身份。
4. `backend/serviceos_api/agents/runtime.py:47` 的常驻提示词也用 S1 Pro 作为同名产品冲突示例，并要求工具返回歧义时澄清。它解释了模型如何学到这组候选，但没有要求模型为无型号的报障查询 S1 Pro。
5. `QueryRewriter` 位于歧义检测之后（`agent_services.py` 的 `detect_ambiguity` 之后才调用 `rewrite`），所以本次前置歧义分支不可能由查询改写补出 S1 Pro。

## 初步判断

**产品误识别：**回复中的两个产品和型号与 `lookup_manual` 的歧义工具结果完全对应，因此工具结果很可能是助手列出这两项的直接来源；但由于没有原始工具参数/检查点，本次只能将其定为高可信推断。已证实的结构性故障点是：模型可自由提供知识工具查询，确定性后端把查询中的型号短语当作真实的产品消歧意图；没有核对该型号是否来自客户陈述、已核验设备或可信上下文。这允许模型臆造/锚定出的 S1 Pro 触发正确但不适用于当前客户意图的候选列表。

较可能的上游诱因是提示词中的 S1 Pro 示例对模型产生锚定，或模型在当前/历史上下文中误选该查询。但本次没有可用的原始 AgentRun、精确 `lookup_manual` 参数、模型输入输出或所用 Provider，因此“模型具体为何生成 S1 Pro”尚未证实。`ToolResult.audit()` 刻意只保存工具名、状态、适用性、references 和 notes，不保存 query；这符合查询隐私约定，但也使普通 AgentRun 结果不能回答这个问题。不能据当前证据断言是知识检索召回、查询改写或前端改写导致。

**危险信号漏检：**这点已由代码确认。公开发布前的 `publish_agent_response()` 会用 `RISK` 对原始用户消息做确定性覆盖，但 `RISK` 当前只匹配“鼓包、冒烟、漏液、烧焦、烫手、异味、异常发热、明显过热、过热”，不匹配“炸了、爆了、爆炸、起火”。因此本次词语不触发后端安全闸。Worker 在调用主 Agent 之前没有安全分流：先完整运行 `AgentRuntime.invoke()`（其 `lookup_manual` 工具始终开放），再进入 `publish_agent_response()`。提示词的富内容安全指导也只列举鼓包、冒烟、漏液、异味、明显过热，没有覆盖爆裂表达。

这不是“已命中安全规则但被型号澄清覆盖”，而是当前确定性检测器没有认出这句危险表达，模型和检索路径因此继续执行。

## 修复方案与实现

沿用现有 Agent 和 Conversation Service，不新增 Agent、HTTP API 或数据库字段：

1. 新增 `application/safety_policy.py`，以统一 `SafetyAssessment` 识别 STOP_USE/EMERGENCY。词表覆盖鼓包、冒烟、焦味、漏液、过热、破损、爆裂、爆炸和起火，直接否定有回归；AgentRun 只保存策略版本、级别和规则 ID，不重复存客户原文。
2. Worker 在调用 `AgentRuntime.invoke()` 前评估本轮原文。命中时生成服务端回复，跳过该轮 ReAct、RAG 和诊断委派；仍把结果写入 AgentRun，并通过现有 `ConversationService` 发布授权、幂等回复。
3. `publish_agent_response()` 和 rich/UI projection 都复核本轮原文。风险态只投影服务端安全告警和人工协助入口，丢弃模型排障内容、型号卡和 quick replies。
4. `lookup_manual` 的歧义判断以客户原文为准，不再以 Agent 自拟的 query 触发产品澄清。对于查询里出现、但用户未提及且无已核验型号支持的已知歧义名，检索回退到本轮客户原文；否认提及该型号的表达不会触发澄清。系统提示词中的具体 S1 Pro 示例已移除。

该策略是 SOP 对齐的受限词语/短语规则，不是通用语义分类器。安全文案不编造地区电话号码；实际地区的紧急服务由本地化配置负责。Agent Worker 当前仍按既有启动约束要求配置 LLM Provider，即便风险首答本身不调用模型。

## 后续取证建议

- 对原始会话的 AgentRun 审计，仅查看允许的工具名称、`lookup_manual` 查询参数是否被脱敏保留、`disambiguation_required`、检索 references 和结构化最终回复；不要导出原始模型推理或其他客户隐私。
- 核对该轮授权上下文是否含历史消息摘要、已关联设备或 Case 文本，以及是否确有任何来源写入 `S1 Pro`。
- 若能在相同 Provider/模型配置下重放，捕获模型生成的工具参数并记录版本；当前隔离环境没有完成真实 Provider 多轮复现，所以还不能证明模型锚定假设。

## 改动与边界

- 修改范围：后端安全策略、Worker、Agent 检索服务、RAG 来源约束、提示词、回复/UI 投影和回归测试；没有 OpenAPI、前端、迁移或生产配置变更。
- 命令：`uv run --project backend --locked pytest backend/tests/test_safety_policy.py backend/tests/test_rich_reply.py -q`，结果 `6 passed`。
- 命令：`uv run --project backend --locked pytest backend/tests/test_safety_policy.py backend/tests/test_rich_reply.py backend/tests/test_worker_runtime.py backend/tests/test_knowledge_retrieval.py -q --require-postgres`，结果 `66 passed`。
- 真实 DeepSeek/其他 Provider 多轮未配置、未执行；无原始事故 AgentRun，故仍不能证明具体模型为何生成 S1 Pro。需要本地化的消防/急救文案与产品安全审核仍待确认。
