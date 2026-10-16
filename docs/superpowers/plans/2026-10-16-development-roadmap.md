# 售后通黑客松交付开发路线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本文件是分阶段路线；进入每个业务切片时，先按仓库协作规范完成该切片的功能契约、设计和细化实现计划。

**Goal:** 在现有真实前后端工程上，交付可从空白状态开始、真实模型参与、人工协作可控、结果可核验且可重复演示的黑客松作品。

**Architecture:** 保留 React 单应用、FastAPI 模块化单体、PostgreSQL、独立 Worker、LangChain/LangGraph 和 REST/SSE。业务写入仍经过应用服务；受控 UI 文档只投影权威状态。真实售后未接入时继续明确标注 Mock。

**Tech Stack:** React 19、TypeScript、Vite 8、TanStack Query、FastAPI、Python 3.12、SQLAlchemy/Alembic、PostgreSQL 17、LangChain/LangGraph、Playwright、现有 Compose/CI。

---

## 规划基线与范围

日期：2026-10-16（北京时间）。代码基线 `1c7da43`。本地工作入口：`D:\Anker黑客松\anker-serviceos`。关联聊天、旧工程保护、克隆与当前 CI 证据见 [本地进度报告](../../local-baseline-2026-10-16.md)。

本次只拉取、核对和规划，没有开始下面的新功能实现。任务顺序代表建议优先级，未勾选项不代表已开发。估时是两位熟悉工程的开发者的工作量参考，不是承诺日期，也不包含等待模型配置或赛事材料确认的时间。

三种推进方式的取舍：继续只润色 UI，工作量较小，但新用户仍可能无法走完流程；优先补齐可演示业务纵切面，最符合当前目标；直接投入生产认证、云部署和真实售后接入，需要外部资源且交付周期更长。**推荐第二种**，在纵切面验收后再做针对性 UI 打磨。

## 里程碑与建议分工

| 顺序 | 工作 | 建议负责方 | 工作量参考 | 必须交付的结果 |
|---|---|---|---|---|
| M0 / P0 | 新目录运行基线 | 集成负责人 | 半天 | 环境、数据库目标、迁移与启动可复现 |
| M1 / P0 | 创建幂等与服务入口 | 业务后端 + 前端 | 1–2 天 | 从页面创建案例并关联会话，可无设备开始 |
| M2 / P0 | 真实模型与协作联调 | Agent/后端 + 前端验收 | 1–2 天 | 多轮诊断、接管、恢复与公开/内部隔离 |
| M3 / P1 | 赛题数据与可重复评测 | Agent/后端 + 业务复核 | 1–2 天起 | 有来源的场景集、受限知识和评测结果 |
| M4 / P1 | 完整流程与 UI 收口 | 前端 + 集成负责人 | 1 天 | 成功与异常路径均能从页面解释和恢复 |
| M5 / P1 | 提交材料和演示排练 | 团队共同 | 半天至 1 天 | 可重置环境、演示脚本、视频/演示稿 |
| M6 / P2 | 经验审核与后续能力 | 按切片分工 | 交付后独立估算 | 经审核经验可操作，后续能力逐项验收 |

M1 与 M2 可在契约稳定后分别推进，最终共同验收。若仍沿用你负责前端、伙伴负责后端的分工，你的第一项是 M1 页面入口，伙伴先处理创建幂等契约及 M2 模型环境；这是建议分工，本次没有向伙伴发送消息。

## Task 0：建立新目录的可运行基线

**现有入口：** `README.md`、`frontend/README.md`、`backend/README.md`、`docs/operations.md`、`compose.yaml`、`backend/serviceos_api/settings.py`、`backend/serviceos_api/operations.py`。

**记录文件：** 新建 `docs/local-runtime-validation-2026-10-16.md`。

- [ ] 记录 Python 3.12、Node 24、npm 11、uv 与 PostgreSQL 17 的实际版本和路径。系统默认 Python 是 3.11；本机可使用已验证的 Python 3.12.14。
- [ ] 选择独立的本地开发库和独立测试库，确认旧预览库归属；如需迁移原数据，先备份再迁移，不能直接重置旧库。
- [ ] 仅在不存在时从 `backend/.env.example` 建立本地 `.env`，保留现有凭据；在新目录恢复锁定依赖。
- [ ] 对独立目标执行 Alembic 升级与本地身份初始化，记录迁移 head。API、前端、inspection/actions/followups/outbox 分别启动并检查心跳。
- [ ] 检查 health、readiness 和数据库；未配 Provider 时如实记录未就绪项。更新运行记录中的实际 URL，不能沿用旧聊天端口作为启动证据。

**验收：** 页面读取真实授权数据，重启后数据保留；数据库目标与 Worker 配置一致；无模型时不生成假回复。使用现有启动说明，无需另造一套启动器。

## Task 1：确认创建与关联的可靠性契约

**现有文件：** `backend/serviceos_api/api/resources.py`、`backend/serviceos_api/application/contracts.py`、`application/business.py`、`persistence/models.py`、`backend/tests/test_business_api.py`。

**新增文档：** `specs/011-service-entry/contracts/feature-contract.md`，编号 011 是本路线建议，实施前确认未被其他分支占用。

| 真实接口 | 当前请求要点 | 前端用途 |
|---|---|---|
| `POST /api/v1/cases` | `problem_text`、可选 `user_goal`；客服必须指定同租户 `customer_id` | 建立一次服务问题 |
| `POST /api/v1/cases/{id}/conversations` | `conversation_id`、`expected_version` | 显式关联已有会话 |
| `POST /api/v1/devices` | 型号或设备标识至少一项；客户归属由后端校验 | 可选创建设备档案 |
| `POST /api/v1/cases/{id}/devices` | `device_id`、`expected_version`、可选 `role`/`is_primary` | 显式关联设备 |

- [ ] 先确认“客户从会话创建案例”为第一条页面路径；无设备身份也允许建立 Case，不默认一段会话只有一个 Case。
- [ ] 将当前缺少创建请求 UUID 的事实写入契约；建议增加客户端创建 UUID、相同请求重放返回原记录、不同内容复用同编号返回冲突。字段、唯一约束与响应状态先由接口使用方共同确认。
- [ ] 后端先覆盖相同请求重放、不同内容冲突、跨客户/租户拒绝、并发创建和响应丢失后查询恢复；再实现应用服务、约束和必要迁移。
- [ ] 为每个关联操作使用上一条成功响应中的最新 Case 版本；409 时刷新并重新选择，不自动重放过期写操作。
- [ ] 决定“Case 已创建但关联失败”的恢复读模型。若现有查询不能确认关联是否已写入，必须补正式读取/恢复契约，不能靠 UI 猜测或重新创建 Case。
- [ ] 按“真实后端 → 导出 OpenAPI → 同步提案 → 生成 Client 类型”发布确认后的契约。

**验收：** 创建/关联结果未知时不会产生重复案例或重复设备；部分成功可继续完成；跨客户和跨租户关联均被后端拒绝。当前已有接口可复用，但不得将未实现的创建幂等能力写成既有功能。

## Task 2：补齐页面服务入口

**修改：** `frontend/src/api/client.ts`、`src/app/queryKeys.ts`、`src/features/conversation/ConversationContext.tsx`、`src/features/cases/CasesWorkspace.tsx`、`src/features/devices/DevicesWorkspace.tsx`。

**建议新建：** `src/features/cases/CaseCreateForm.tsx`、`CaseLinkPanel.tsx`、`src/features/devices/DeviceCreateForm.tsx`、`frontend/tests/service-entry.spec.ts`。组件遵循现有表单和状态样式，避免重做五个页面。

- [ ] 先写失败用例：当前会话创建无设备案例，问题描述和服务目标在提交失败后保留。
- [ ] 接入已确认契约的创建与关联 Client；只使用生成类型。对创建操作关闭隐式网络重试，稳定保存本次请求编号。
- [ ] 在会话资料区提供“新建服务案例”和“关联已有案例”，在 Case/Device 页面增加明确入口；设备身份保持待核验，用户输入不自动成为 VERIFIED。
- [ ] 关联会话后，可选关联已授权设备或新建设备；新建设备失败不撤销已成功创建的 Case。
- [ ] 对加载、空态、提交中、422、403/404、409、网络未知结果分别显示下一步；刷新相关 cases、summaries、devices 和 deviceCases 查询。
- [ ] 通过真实 API 从空白客户账号完成流程，刷新后仍能从会话进入同一个 Case；另一客户不可访问其案例或设备。

**验收：** 用户无需控制台、手动 API 或预置 Case 即可完成“描述问题 → 建立会话 → 建立案例 → 可选关联设备 → 上传证据”。覆盖桌面和 390px 手机、键盘操作及无障碍检查。

## Task 3：真实模型、多轮服务与人工协作验收

**现有文件：** `backend/serviceos_api/agents/runtime.py`、`application/agent_services.py`、`application/skills.py`、`worker/main.py`、`worker/runtime.py`、`frontend/tests-live/service-flow.spec.ts`。实施时先确认 Worker 文件职责，不直接修改业务表。

**记录：** 新建 `docs/provider-acceptance.md`；可复现配置仅给变量名称，不写密钥。

- [ ] 确认实际模型、API 地址、数据处理范围与预算，把凭据放本地环境；初始化独立 Checkpointer，启动 Agent Worker。
- [ ] 以一个有知识依据的型号运行多轮服务：缺证据时追问、工具返回有来源、消息快速受理，后续输出由持久事件驱动。
- [ ] 客户请求人工，由客服接管到 CO_SERVICE/HUMAN_LEAD；保留内部建议，验证旧 Agent 和待发布公开结果仍被最新发言策略约束。
- [ ] 在明确隔离的测试环境验收刷新、SSE 断线补取、模型超时、Worker 被终止后的租约恢复；按原请求核对副作用，没有重复消息或动作。
- [ ] 复验 T8D04 指标图的已核验型号/来源限制与客服流程图 INTERNAL 隔离。CI 渲染通过不能替代真实模型选择组件的质量。
- [ ] 对“明确不满、困惑、着急、反讽/转述、普通提问”人工评估回应指导；不能由情绪线索改变业务权限或承诺售后时限。

**验收：** 至少一条真实模型闭环和一条故障恢复有可复现实录；记录模型/版本、输入场景、工具调用摘要、公开与内部结果、耗时和结论，不保存密钥或原始思维链。CI 无真实 Provider 的测试替身不作为此项完成证据。

## Task 4：把官方材料变成受限知识与评测

**来源：** `data/reference/hackathon/README.md`、同目录官方 Word/Excel；现有运行时知识在 `backend/serviceos_api/knowledge/`。本路线依据资料说明整理范围，未重新逐条审阅 Word/Excel 中的全部内容。

**建议新增：** `data/evaluation/service-cases.jsonl`、`data/evaluation/README.md`、`backend/tests/test_hackathon_scenarios.py`。正式订单/经销商接口另立功能契约，不能直接添加可成功调用的空端点。

- [ ] 建立材料到场景的清单：shipping、product inquiry、troubleshooting；保留来源文件、工作表、行号、产品型号、预期下一步和资料缺口。
- [ ] 先精选 15 个可人工复核的场景作为首批冒烟集，每类至少 3 个，其余覆盖资料不足、跨型号、拒绝及人工接续。15 是本项目建议值，不是赛事官方验收门槛。
- [ ] 从 Published/Visible 问答中只提取已核对型号、版本和适用范围的条目；保留来源与版本，不把订单表或全部 Excel 直接复制进 Runtime。
- [ ] 如选择演示订单查询或经销商匹配，建立只读静态资料适配器，清楚标记数据快照；国家精确匹配，Seller 有歧义时追问，不能冒称实时订单查询。
- [ ] 记录回答依据正确率、缺证据追问、跨型号误引用、虚构业务完成、人工接续及敏感动作越权；同时记录样本量和失败样例，不能用单一模型自评分宣布达标。
- [ ] 固定开发集与保留验证集，避免只针对演示脚本调参；复验后决定是否扩充检索范围。

**验收：** 任何运行时知识都能追溯来源、型号与适用范围；首批评测可重复运行，有失败分类。现有 63 条工单不直接等同于赛题说明中的“40+10”标注集。

## Task 5：完整业务流程与 UI 收口

**修改范围：** 以 `frontend/src/features/cases/`、`features/collaboration/`、`features/ui-document/` 和现有三份 CSS 为主；相关后端规则复用现有应用服务。

**记录：** 新建 `docs/end-to-end-demo-validation.md`，更新 `docs/ui-backend-map.md` 中因资源路由拆分或新入口发生变化的映射。

- [ ] 走通成功路径：报障 → Case/设备关联 → 图片证据 → 真实模型排查 → 人工协作 → 独立审批 → 明确 Mock 回执 → 客户核验 → 合格事实归档。
- [ ] 走通拒绝/未解决：审批拒绝和客户未解决时不进入 RESOLVED，不提前归档 Case 来源事实。
- [ ] 走通失败/未知：Worker 失败展示真实状态；UNKNOWN 只对账，不重新提交外部动作；断线后恢复到服务端状态。
- [ ] 让页面明确指出下一位操作人、所需资料和当前阻塞；空态给真实下一步，统计仍只代表当前加载授权记录。
- [ ] 检查桌面/手机的创建表单、对话、详情、审批和核验；修复实际发现的拥挤、溢出、焦点或对比度问题，再更新截图。

**验收：** 成功、拒绝、失败、未知结果均有从页面出发的证据；客户不见内部备注/流程图；提出动作、批准、执行与解决四个阶段始终可区分。

## Task 6：演示提交与冻结

**新增：** `docs/hackathon-demo-script.md`、`docs/hackathon-submission-checklist.md`；更新 `README.md` 和已有验收索引。

- [ ] 从正式赛事说明核对提交格式、时长与截止时间，记录来源；本路线不假设具体赛程。
- [ ] 编写约 5 分钟可调整的演示脚本：问题价值 → 客户报障 → 人机协作 → Mock 办理 → 客户核验 → 来源与审计；备有不依赖现场网络的视频。
- [ ] 使用现有受守卫的 operations/Compose seed 路径准备可重复演示资料；重置只针对明确隔离的演示目标，保留原始数据和验证证据。
- [ ] 完成下方检查，等待对应提交 CI 实际通过；提交候选代码变更时用短分支与 PR，附实际证据，冻结演示版本。
- [ ] 在干净环境排练一次启动、演示、重启与重新演示；材料注明模型、图片检查、静态资料和 Mock 边界。

**验收：** 另一位开发者可按 README 恢复环境，评委可理解完整流程与数据来源；演示稿、视频和代码展示的能力一致。

## 统一验证命令

在确认 `SERVICEOS_TEST_DATABASE_URL` 指向可创建/删除独立测试数据库的本地测试 PostgreSQL 后，从仓库根运行：

```powershell
uv run --project backend --locked pytest backend/tests --require-postgres
uv run --project backend --locked python -m serviceos_api.export_openapi --check
uv run --project backend --locked python contracts/proposed/v1/sync_implemented.py --check
```

在 `frontend/` 运行：

```powershell
npm run check:api
npm run typecheck
npm run build
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:browser
```

预期：检查退出码 0，受影响场景不跳过。当前远端基线是 219 项后端、85 项受控前端、6 项真实浏览器通过；新增测试后数量可增加，不锁死旧计数。

`npm run test:live` 按 `frontend/README.md` 在独立开发库与空闲的 8000/5173 端口运行，避免指向旧预览库或复用日常服务器。真实 Provider 和杀进程恢复另按 Task 3 记录，不能用此命令代替。

## P2 与生产化边界

先独立交付经验候选列表、编辑、提交、主管审核/撤销 UI，复用 `/api/v1/experience-candidates` 与现有权限/版本规则。然后按明确需求处理回访撤回/改期/取消、图片多模态与安全扫描、更多图表来源；每项先做功能契约与成功/拒绝/恢复验收。

生产身份、真实 Anker/物流/售后接入、生产对象存储、云 HTTPS/备份/监控属于后续独立阶段。它们有各自外部资源与权限要求，不应因黑客松演示目标自动启动。

**建议紧接着执行：M0 运行基线，然后完成 M1“创建幂等与服务入口”的契约及页面纵切面。** 最新后端 CI 已绿，无需继续把旧的 8 项失败当作开工前置任务。
