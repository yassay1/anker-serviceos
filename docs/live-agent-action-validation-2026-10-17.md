# 后端真实 Agent 售后动作链路验收（2026-10-17）

> 状态更新（2026-10-17）：下文为历史探针记录。用户随后决定不采用固定客户兜底话术，并移除实体接地检查对常规回复的实时阻断；主 Agent Prompt 负责提醒不虚构型号/数字并标注推断。公开权限仍由后端协作策略授权。当前行为以 [S1 闭环核功能契约](../specs/015-s1-loop-guard/contracts/feature-contract.md) 和代码为准。

## 范围与测试环境

本次只测后端：真实 FastAPI 路由（`TestClient` 直连 ASGI 应用，不经过浏览器或外部 HTTP 服务器）、隔离 PostgreSQL、真实配置的 LLM Provider、`MessageWorker`/`AgentRuntime`、主管审批应用服务、`MockActionWorker` 和客户结果核验 API。未启动浏览器，也未调用真实 Anker 售后系统。

数据库运行在临时容器 `127.0.0.1:55433/serviceos_dev`，数据目录为 tmpfs；迁移至 `0021_interaction_align`，播种本地体验身份，初始化 LangGraph checkpoint 并导入只读知识（6 个种子文档、1235 个分段）。结束后删除临时容器即可清除本轮业务记录，不影响现有 `55432` 开发库。

测试入口：[manual_real_provider_chain.py](../backend/tests/manual_real_provider_chain.py)。脚本要求显式设置 `SERVICEOS_LIVE_AGENT_PROBE=1`，并拒绝连接非回环地址或非 `127.0.0.1:55433/serviceos_dev` 数据库；必须使用开发/测试身份及已配置 Provider。脚本触发真实模型调用，但售后操作固定走 `MOCK` Adapter。

## 可复现输入

来源：[官方赛题资料](../data/reference/hackathon/README.md)，Excel“客诉工单”第 28 行。使用 E25 / 错误码 3212 滚刷堵塞案例；原记录中的序列号没有复制到测试消息。输入复述：

> Omni E25 提示滚刷堵塞（3212）。客户已按建议清理，未看到堵塞，但拖地清洁后持续出现重复的开裂声，吸尘器无法启动；客户明确要求提交维修申请。

## 实际链路结果

两次独立 AgentRun 都实际调用了受限 `request_mock_service_action` Tool。一次运行的记录如下：

| 环节 | 实际结果 |
|---|---|
| 客户消息受理 | `POST /conversations/{id}/messages` → 202；本次受理 24.71 ms |
| Agent Worker | `COMPLETED`，无错误码，9 steps；本轮耗时 17.52 s |
| Tool 写入 | 由服务端关联 Case/Conversation/AgentRun，动作创建为 `WAITING_APPROVAL`，`adapter=MOCK`；确认 `requested_by_agent_run_id` 指向本轮 AgentRun |
| 主管审批 | `POST /approvals/{id}/decisions` → 200，状态 `APPROVED` |
| 模拟动作 Worker | 领取并执行；动作 `SUCCEEDED`，回执 `adapter=MOCK` / `result=SUCCEEDED` |
| 客户核验 | 客户提交 `WORKING` → 201；Case 服务端转为 `RESOLVED` |

两次运行的关键记录：

| 运行 | Case | Conversation | AgentRun | Action | Guard 未依据承诺数 |
|---|---|---|---|---|---:|
| 1 | `4e6dd8ae-b3e8-4ce8-9dcc-cd138f05730d` | `39253b2a-bcbb-474b-a37f-64a9f5467f9a` | `fdef571b-1647-438e-a6b5-2e4b6e59c7f0` | `eedec49e-c759-4146-b020-d7f204220155` | 2 |
| 2 | `90f5c241-2687-4285-98c6-b6d24e1ddd82` | `54f1bc42-88ed-4cf7-aba6-13156ee7fbb2` | `6c1b94fc-127d-4628-aa56-68f36763f121` | `ec308651-6e02-4852-8529-80a9a4510ff4` | 1 |

第二次运行最终核验 ID 为 `ce950afe-77e8-43d2-85f1-7087bbbf2974`。这些 ID 只在本次临时数据库有效。

## 发现的问题

**主问题：Agent 已创建动作，但客户收不到 Agent 的待审批说明。** 两次 AgentRun 均完成并留下动作；客户消息 API 没有返回任何 Agent `PUBLIC` 消息。数据库中保存的是 `INTERNAL` Agent 回复。发布守卫记录为 `BLOCKED` / `UNCOVERED_REQUEST`；覆盖核验报告 `unaddressed=0`，但判定回复包含 1–2 条未依据支持的承诺。Fail-closed 阻止了该回复外发，这个安全行为正确；缺少可公开的保守降级答复导致客户侧业务闭环不完整。脚本把“无公开回复/未说明待审批”作为失败，所以本次真实 Provider 探针退出码为 1，属于发现缺陷，不是成功验收。

**次要信号：手册检索命中不相关资料。** 同一 AgentRun 对 `lookup_manual` 的引用落在官方赛题数据的经销商目录行，而输入是 E25 故障处理。应进一步检查查询改写/混合检索对低相关结果的过滤；本次未据此回答任何已验证设备事实。

## 当前结论与限制

- 已验证 Agent → 类型化 Tool → 持久待审批动作 → 主管授权 → 独立 Mock Worker 回执 → 客户核验的后端业务状态链可执行。
- 整体演示链**未通过**：Agent 的待审批客户答复被发布守卫拦截，没有自动生成安全、可公开的 fallback；Action/Case 状态链成功不能掩盖这一点。
- 本次是本机测试身份与 Provider 调用，不代表生产身份、生产模型质量、真实 Anker 系统或实际维修完成。
- 知识摄取显示 `embedded now: 0`；本次 Agent 调用走现有索引/知识环境，不把该运行结果视作新建全量向量索引的验收。

## 执行命令

先建隔离 PostgreSQL 并执行项目 README 的迁移、`bootstrap_local`、`checkpoints` 与 `knowledge_ingest` 初始化。然后在仓库根目录加载 `backend/.env` 的 Provider 配置（不把密钥写进命令历史），覆盖数据库地址到隔离端口并运行：

```powershell
$env:SERVICEOS_DATABASE_URL='postgresql+psycopg://serviceos_local:<local-password>@127.0.0.1:55433/serviceos_dev'
$env:SERVICEOS_ENV='test'
$env:SERVICEOS_AUTH_MODE='local'
$env:SERVICEOS_LIVE_AGENT_PROBE='1'
uv run --project backend --locked python backend/tests/manual_real_provider_chain.py
```

脚本预期在链路状态正确但客户回复被守卫拦截时以非零状态退出，并打印包含对象 ID、状态、守卫原因和耗时的 JSON，便于复现和比对。

## 历史后续修复记录（已被后续决策替代）

当时曾尝试修复“守卫拦截后没有客户可见答复”的断点：当被拦截的 AgentRun 恰好关联当前会话中的一条 `MOCK_SERVICE_REQUEST`，且本轮不是安全停止时，Conversation Service 按持久动作状态选择固定中文说明。文案明确这是模拟动作，并区分待审批、已批准、执行中、未知、成功、失败和拒绝；成功回执仍不表述为 Case 已解决。这是阶段性工作树实现，不是当前采纳的产品方案。

这段记录了当时的临时方案，不代表当前代码仍会公开该 fallback。之后用户明确要求不做兜底，因此该实现及对应测试已从当前工作树撤回。当前实时守卫只按确定性实体证据检查决定 `PASSED/BLOCKED`；语义覆盖和承诺检查不再同步调用模型或阻断发布。

```powershell
$env:SERVICEOS_TEST_DATABASE_URL='postgresql+psycopg://serviceos_local:serviceos_local_only@127.0.0.1:55432/serviceos_dev'
$env:SERVICEOS_ENV='test'
$env:SERVICEOS_AUTH_MODE='disabled'
uv run --project backend --locked pytest backend/tests/test_loop_guard.py backend/tests/test_mock_service_actions.py backend/tests/test_worker_runtime.py --require-postgres -q
uv run --project backend --locked ruff check backend/serviceos_api/application/services.py backend/tests/test_loop_guard.py
```

结果：80 个受影响后端测试通过，Ruff 检查通过。这是旧临时 fallback 实现的历史测试结果，不能作为当前验收结果。

## 2026-10-17 实时守卫收窄修订

- 实时发布只运行确定性实体依据检查；不再调用语义 CoverageVerifier，Provider/verifier 不可用不会额外拦截回复。
- 未依据的型号、日期、带单位数值和错误码仍可触发 `UNGROUNDED_ENTITY`，回复保留为 INTERNAL 草稿供主管复核。
- 不生成客户兜底消息。语义覆盖和承诺质量通过离线多轮数据集观察，不冒充实时安全授权。
- 验证：`pytest backend/tests --require-postgres -q` 为 359 passed、2 条既有 PostgreSQL/迁移警告；守卫定向测试 9 passed；Ruff、前端 typecheck/build/API check 通过。未重新调用真实 Provider。
- 未实现范围：无结构化证据引用的业务结果陈述（例如“已退款”）需要后续建立类型化主张与已授权动作/真实回执的关联；本次没有添加可能误判的自由文本规则。
