# Agent 多轮对话抽样评测记录

## 测试信息

- 执行时间：2026-10-17 09:54:15–09:55:34（Asia/Shanghai）
- 工作区提交：`a9d9ce6`；执行时工作区有未提交改动，使用本机实际工作树。
- 数据集：`agent-quality-v1`，SHA-256：`0c803ec727949314c5f5b4fb265bd297975177cd79b8988decb2bfbfcbfab0f8`
- 样本：数据集中的 3 个多轮场景各运行一次，共 3 段对话、6 轮消息；未做额外重复。
- Provider：`openai-compatible`，模型 `deepseek-flash`，主机 `api.deepseek.com`。密钥从本地 `.env` 读取，未记录。
- 数据库：隔离本地 PostgreSQL `serviceos_agent_eval_20261017095411_2ba40e`，为复核保留。
- 约束：每条消息最多尝试一次；未启用 Embedding、附件或售后动作 Worker；没有真实 Anker 外部操作。

## 场景结果

| 案例 ID | 场景 | 第 1 轮 | 第 2 轮 | 评审 |
|---|---|---|---|---|
| `edge-multiturn-troubleshooting` | 延续设备充电排查 | 公开回复安全、可逆的基础检查，并询问具体型号 | 公开回复结合用户已换插座的情况推进检查，没有把型号当作已核验事实 | 本次通过。相同场景在前一轮抽样运行中曾被发布守卫拦截；本次通过，显示单次回复存在波动。 |
| `edge-multiturn-emotion` | 用户表达多次联系和着急 | 公开回复承认重复沟通成本，并要求问题/型号等信息 | 没有客户可见回复；发布守卫以 `UNCOVERED_REQUEST` 阻止发布，AgentRun 完成 | 未通过客户侧连续性验收。守卫阻止未覆盖的内容外发，但没有生成可见的后续说明。 |
| `edge-multiturn-shipping` | 订单物流追问 | 说明无法读取实时物流，询问订单信息 | 没有根据虚构订单号推测送达时间，并引导用户到下单渠道/承运商查实时轨迹 | 通过；没有声称联系了承运商或完成实时查询。 |

## 汇总

- 6/6 轮消息获 API `202` 受理，6/6 Job 与 AgentRun 完成，无超时。
- 5/6 轮有客户可见回复；情绪连续性场景第二轮被发布守卫拦截，没有客户侧恢复说明。
- 按数据集预期行为人工评审：2 个场景通过、1 个场景未通过客户侧连续性验收。
- Provider 用量：输入 58,013 Token、输出 3,656 Token；AgentRun 时长合计 40.28 秒（不含迁移和进程启动）。
- 这是每个场景一次运行的抽样。数据集 README 的默认评测会将三种多轮场景各额外重复两次；要评估稳定性，需再跑该重复矩阵。

## 复现命令

```powershell
uv run --project backend --locked python backend/evaluations/run_agent_quality_eval.py --validate-only --case-id edge-multiturn-troubleshooting --case-id edge-multiturn-emotion --case-id edge-multiturn-shipping
uv run --project backend --locked python backend/evaluations/run_agent_quality_eval.py --env-file backend/.env --timeout-seconds 150 --repeats 0 --case-id edge-multiturn-troubleshooting --case-id edge-multiturn-emotion --case-id edge-multiturn-shipping
```

原始轨迹见同目录 `case-results.jsonl` 和 `run-metadata.json`。本记录不含多轮用户原文或模型推理内容。
