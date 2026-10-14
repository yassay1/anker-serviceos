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

2026-10-12 阶段 1 本地验收完成，证据见 [阶段 1 验收记录](phase1-validation.md)。该记录中的后续能力描述是当时的状态；当前阶段 2–3 的完成范围分别见下文及对应验收记录。生产认证与阶段 4 业务动作仍待实现。

## 2. Agent 闭环

- [x] Worker 的持久化任务租约、心跳、退避重试、过期恢复、终态和 Outbox
- [x] LangChain `create_agent` 与独立 PostgreSQL Checkpointer schema 接入（需显式初始化）
- [x] 授权 Context Builder、受限本地 SOP 检索
- [x] AgentRun 审计、模型请求 timeout、模型调用/工具步数限制、单次输出 token 上限和失败处理
- [x] 受控工具 `lookup_manual`, `request_missing_evidence`, `propose_action`；后两项只记内部草稿，不执行或公开
- [x] 定义文本、`ui_proposal`、`action_proposals` 分离的结构化运行结果；UI proposal 失败可退回文本（内部结果契约；UI 发布/Renderer 属阶段 3）
- **验收**：真实 LLM 处理多轮售后问题，刷新不丢运行状态；无需在本阶段实现多模型框架对比

2026-10-13 阶段 2 的代码与离线 PostgreSQL 验收已完成，详见 [阶段 2 验收记录](phase2-validation.md)及[结果分离切片](../specs/001-agent-result-separation/spec.md)。当前本地没有模型 Provider 凭据；真实 LLM 多轮、Provider 兼容性与进程级中断恢复演示尚未执行，不以测试替身冒充。因此阶段 2 的真实 Provider 验收门槛尚未关闭。

## 3. 真人与 Agent 共同服务

- [x] `/desk` 同租户会话列表和内部备注（阶段 1 已验收）
- [x] `/desk` Case 事实摘要与来源、核验状态展示
- [x] 协作模式和发言策略、后端二次授权、切换版本冲突处理
- [x] 人工任务、审批结果、Agent 恢复
- [x] 公开消息/内部消息隔离，SSE 断线补取
- [x] 版本化 UI Schema、受信组件 Catalog 与服务端 Schema/Policy Validator
- [x] `/support`、`/desk` Renderer：未知组件、断线或不支持时降级到文本/固定表单
- [x] UI action intent 经类型化 API 回到应用服务，重新校验 actor、版本、Rule、审批与幂等
- **验收**：Agent → 协同 → 真人主导 → Agent 恢复；真人介入不要求用户重述；后台 Agent 不偷发消息

2026-10-13 阶段 3 功能代码、PostgreSQL 回归、迁移、OpenAPI/Client 与前端构建已通过，详见 [阶段 3 验收记录](phase3-validation.md)；`/support`、`/desk` 的浏览器端到端成功、拒绝和恢复路径仍待复验。以上勾选表示对应功能已实现并通过所记录的本地检查，不表示浏览器路径或真实 Provider 验收通过。阶段 2 的真实 Provider 仍为“待验”；阶段 4 的外部动作、真实回执与核验闭环尚未实现。

## 4. 完整售后演示闭环

2026-10-14：图片证据的后端受理、本地结构检查和下载授权已有真实路由与 PostgreSQL 测试。开发环境文件存于私有本地目录，数据库保存对象引用；生产对象存储适配器未配置。10 MiB、JPEG/PNG/WebP 和扫描阈值仍是待确认提案，多模态理解与完整安全审查未做，因此下面各项保持未勾选。阶段 2 的真实 Provider 验收继续为“待验”。

阶段 4 增量：`MOCK_SERVICE_REQUEST` 已有开发环境实际路由、独立审批、Worker、持久模拟回执和 UNKNOWN 查询对账；`/cases` 显示动作与角色化审批。其具体业务语义及角色仍属待产品确认的拟定契约，尚未接结果核验、跟进或真实 Anker 服务，因此完整动作与核验闭环仍未完成，以下勾选不提前关闭。

图片证据增量：`/cases` 已接真实上传、检查状态与授权预览，并用服务器返回的客户端证据编号对账未知上传。`CLEAN` 仅代表本地结构检查通过；未实现恶意内容扫描、多模态理解或生产对象存储，图片类型和大小限制仍是拟定值，因此“图片和必要多模态理解、安全审查”仍未完成。

动作后结果保护增量：只要 Case 曾发起模拟售后动作，旧客服状态接口就不能凭动作终态回执直接标为 `RESOLVED`，必须等待正式结果核验服务接入。该保护覆盖模拟成功、失败及拒绝；核验规则与写入入口尚未实现，不能将此保护当成已完成核验。

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
