# 售后通 · 开发实施计划 V1

> 本计划以真实 Agent + 真人协作 + 可核验服务为终点，不安排 Parlant / LangGraph 对比 Spike。各阶段以功能验收为准，不堆砌预先用不到的模块。

> 本仓库采用说明（2026-10-12）：源文件的完成标记不代表此目录实现状态。本地勾选以实际验收为准；新旧衔接及当前范围见 [合并计划](baseline-integration.md)。

## 0. 基线/工程初始化

- [x] 项目背景、领域架构、用户流程与接口草案文档
- [x] 仓库内前后端独立目录，FastAPI 健康接口及最小 React 页面骨架
- [x] 从 FastAPI 代码导出当前已存在 API 的 OpenAPI
- [x] 安装/锁定前端依赖并完成构建（npm ci 已验证）
- [x] 完成生成 TypeScript SDK 并验证生成物；加 CI 的生成契约一致性检查
- [x] 确定 Python/Node 的正式受支持版本与锁文件

2026-10-12 阶段 0 本地验收完成；CI 已配置，尚未在远端运行。详见 [实际验收记录](baseline-validation.md)。健康 API、Web 入口和契约生成不等于阶段 1–5 的业务能力已实现。

## 1. 业务底座：Conversation / Case / Device

- [x] PostgreSQL SQLAlchemy Models + Alembic Migration
- [x] 显式认证、客户/客服权限及租户校验（本地开发适配器；生产身份源待接）
- [x] Conversation 与 Message REST API（idempotent）
- [x] Case、Device 独立 CRUD、案例-设备关系
- [x] User UI 发送消息并显示正确服务器回执
- **验收**：数据库数据可恢复，用户之间绝不串数据，Case 不依赖 Device 完整身份才能建立

2026-10-12 阶段 1 本地验收完成，证据见 [阶段 1 验收记录](phase1-validation.md)。阶段 2 已实现独立 Worker 与受控 Agent Runtime；真实 Provider 多轮验收仍待显式配置模型服务。生产认证、SSE、协作审批及业务动作仍在后续阶段。

## 2. Agent 闭环

- [x] Worker 的持久化任务租约、心跳、退避重试、过期恢复、终态和 Outbox
- [x] LangChain `create_agent` 与独立 PostgreSQL Checkpointer schema 接入（需显式初始化）
- [x] 授权 Context Builder、受限本地 SOP 检索
- [x] AgentRun 审计、模型请求 timeout、模型调用/工具步数限制、单次输出 token 上限和失败处理
- [x] 受控工具 `lookup_manual`, `request_missing_evidence`, `propose_action`；后两项只记内部草稿，不执行或公开
- [ ] 定义文本、`ui_proposal`、`action_proposals` 分离的结构化运行结果；UI proposal 失败可退回文本
- **验收**：真实 LLM 处理多轮售后问题，刷新不丢运行状态；无需在本阶段实现多模型框架对比

2026-10-13 阶段 2 的代码与离线 PostgreSQL 验收已完成，详见 [阶段 2 验收记录](phase2-validation.md)。当前本地没有模型 Provider 凭据；真实 LLM 多轮、Provider 兼容性与进程级中断恢复演示尚未执行，不以测试替身冒充。

## 3. 真人与 Agent 共同服务

- [ ] `/desk` 会话列表、内部备注、事实摘要
- [ ] 协作模式和发言策略、后端二次授权、切换版本冲突处理
- [ ] 人工任务、审批结果、Agent 恢复
- [ ] 公开消息/内部消息隔离，SSE 断线补取
- [ ] 版本化 UI Schema、受信组件 Catalog 与服务端 Schema/Policy Validator
- [ ] `/support`、`/desk` Renderer：未知组件、断线或不支持时降级到文本/固定表单
- [ ] UI action intent 经类型化 API 回到应用服务，重新校验 actor、版本、Rule、审批与幂等
- **验收**：Agent → 协同 → 真人主导 → Agent 恢复；真人介入不要求用户重述；后台 Agent 不偷发消息

## 4. 完整售后演示闭环

- [ ] 用户上传图片和必要多模态理解，安全审查
- [ ] Mock 售后业务 API（明确模拟标签、幂等、回执）
- [ ] 结果核验与后续任务、Device 可信事实归档
- [ ] 用户侧身份/证据/步骤/核验/风险卡与客服侧摘要/Skill/审批/流程卡完整纵切面
- [ ] 评测用案例集、可复现实例、动作审计和指标
- **验收**：从报障到诊断、协作、动作、核验；失败/拒绝分支同样可运行

## 5. 交付/部署

- [ ] Dockerfiles + Compose 本地集成环境（生产/开发配置分离）
- [ ] EC2/Nginx HTTPS，RDS 网络、备份、安全组权限，S3 受控上传
- [ ] 日志脱敏、端到端性能验收、依赖安全检查
- [ ] 演示数据清理和重置脚本

## 响应性能采集指标

`http_accept_ms`, `queue_delay_ms`, `agent_first_progress_ms`, `model_ttft_ms`, `tool_latency_ms`, `mode_sync_ms`, `ui_action_completion_ms`, `error_rate`, `duplicate_action_count`, `ui_schema_validation_error_rate`, `ui_fallback_rate`, `ui_action_rejected_stale_rate`；分 P50/P95 统计，不能用单次顺利演示替代指标，也不能把组件已渲染当作业务完成。

## Agentic Interface 实施顺序

1. 先在阶段 2 增量中稳定结构化 Agent 输出、Context 权限和审计，不修改 Case/Conversation 对象关系。
2. 在阶段 3 建立最小 Catalog（信息、提问、证据、风险、进度）和只读 Renderer，再接 action intent。
3. 先交付低风险用户取证与客服摘要；审批、外部动作和核验组件随对应业务服务在阶段 3–4 接入。
4. 每类组件同时验收 PUBLIC/INTERNAL 隔离、过期 revision、降级、移动端和无障碍。
5. 只有真实 Pydantic/OpenAPI 契约与应用服务存在后才发布接口，不注册空壳端点。

## Codex 单阶段执行原则

一次任务只做明确阶段，先读取 `AGENTS.md` 与 docs，列出将修改的文件，完成实际代码/测试/校验后报告具体命令、结果和未完成项。不许通过 Mock 假装接入真实 Anker 售后后端。
