# 计划：基于真实链路优化 ServiceOS SSE

## 目标

先建立当前 SSE 的延迟、连接和数据库负载基线，再以最小改动降低事件扇出和阻塞风险；完整保留持久事件、授权过滤、断线重连和补取语义。

## 下一步

按本计划实施和验证已完成。后续用 `uv run --project backend --locked python -m serviceos_api.operations metrics --log <JSONL>` 汇总部署后的安全统计，再基于真实连接数和数据库负载决定是否引入通知唤醒。

## 当前阶段

原 SSE 基础优化及本次 Agent 回复耗时诊断、授权回复增量呈现均已完成。

## 各阶段

### 后续阶段 10：内容接地检查与公开回复解耦 — complete
- [x] 检查用户报错会话的客户消息、AgentRun、发布守卫决策、消息可见性与事件发布记录。
- [x] 按用户反馈移除固定兜底话术和实体检查对常规 Agent 回复的实时阻断。
- [x] 在主 Agent Prompt 指导其不虚构型号/数字、标注未核实推断；公开权限仍由后端 AI_LEAD + AI_AUTO 策略控制。
- [x] 检查当前会话的已发布澄清回复及 Outbox 记录；不重跑模型。
- [x] 验证 PostgreSQL 授权发布与接地诊断路径、Prompt 指导、Ruff 和 whitespace。
- **状态：** complete

### 阶段 1：真实链路审计 — complete
- [x] 核对 Outbox 写入/派发、ConversationEvent 序号与可见性读取
- [x] 核对 FastAPI StreamingResponse、每连接轮询、身份复核与代理配置
- [x] 核对 React EventSource、Last-Event-ID、本地游标、历史补取和 query cache 失效
- **状态：** complete

### 阶段 2：一手资料研究 — complete
- [x] 对照 WHATWG/MDN 的 SSE 重连、游标和 keepalive 语义
- [x] 对照 FastAPI/Starlette 的流式生成与线程池行为
- [x] 对照 PostgreSQL LISTEN/NOTIFY 的事务、竞态和 payload 限制
- [x] 对照 TanStack Query 活跃 query invalidation 与 Nginx buffering 行为
- **状态：** complete

### 阶段 3：形成可审查的实施计划 — complete
- [x] 先量基线，区分 Outbox 派发、SSE 传输、浏览器刷新三个延迟段
- [x] 优先评估事件类型化/合并的前端缓存失效
- [x] 评估 async SSE 路径里的同步数据库 I/O，设计线程池卸载与断连回收验收
- [x] 仅在基线证明必要时考虑 PostgreSQL 通知唤醒，持久事件表始终是事实源
- [x] 列出涉及模块、测试、验收、风险和不做事项
- **状态：** complete

### 阶段 4：用户确认 — complete
- [x] 用户审核并确认按计划执行
- **状态：** complete

### 阶段 5：按确认后的计划实施 — complete
- [x] 增加隐私安全的 SSE 连接、轮询/事件批量和延迟统计，取得当前基线
- [x] 完成事件类型化的前端缓存失效与短窗合并
- [x] 将 SSE 中同步认证/事件页读取从 ASGI event loop 卸载到 worker thread
- [x] 根据基线判断 PostgreSQL 通知唤醒是否必要；当前证据不支持增加通知基础设施
- **状态：** complete

### 阶段 6：验证与交付 — complete
- [x] 完整运行后端 PostgreSQL 测试、前端浏览器回归、API 类型和生产构建
- [x] 比较 1/10/50 并发 SSE 空轮询分位数与前端 burst HTTP 刷新次数
- [x] 确认 111 条测试流在两轮空轮询后关闭且无活跃流计数残留
- [x] 记录真实实现范围、观测字段、部署限制和未测项目
- **状态：** complete

### 后续阶段 7：回复等待时间根因 — complete
- [x] 依据真实 AgentRun/MessageJob 时间戳、Worker 状态和模型耗时区分排队、模型生成、发布检查、事件派发与前端刷新延迟。
- [x] 检查开发启动器是否默认启动 Agent Worker，并确认不会在无授权时触发模型费用。
- **状态：** complete

### 后续阶段 8：授权回复增量呈现 — complete
- [x] 设计仅呈现通过 Conversation Service 发布检查的最终公开回复；不把未审查模型 token 暴露给客户。
- [x] 基于持久 SSE 事件向前端分段传输已授权回复，并在 UI 中增量呈现、断线后回退到 canonical message。
- [x] 增加权限、顺序、重复/重连及展示完成状态测试。
- **状态：** complete

### 后续阶段 9：验证与交付 — complete
- [x] 跑定向后端/前端测试、完整前后端检查和构建。
- [x] 报告模型等待与安全呈现耗时的区别、变更文件、命令、结果及限制。
- **状态：** complete

## 续项验收记录

- 实际会话的 `MessageJob` 曾 QUEUED 且 attempts=0、无 AgentRun；Agent Worker 缺失。启动后 AgentRun 到回复保存约 7.2 秒。开发启动器的 Agent Worker 默认 opt-in，未擅自改 `.env` 或启动默认值。
- `agent.reply.delta` 只从通过安全发布门并已保存的 PUBLIC AGENT 消息切片创建；分片、Message 和 `message.created` 同事务持久化。Outbox 顺序、分片来源校验和客户可见测试通过；SSE 逐帧传输后由 `message.created` 刷新规范消息。
- 完整后端 PostgreSQL 测试 360 passed、2 warnings；OpenAPI matches actual application。完整前端 browser 95 passed；API types、typecheck、build 通过。补充修改后定向后端 2 passed、前端流式回归 1 passed、Ruff 和 `git diff --check` 通过。
- 发布门禁调整后再次完成全量验证：Ruff 通过；后端 PostgreSQL 测试 360 passed、2 warnings；OpenAPI 检查通过；前端 API 类型检查、typecheck、production build 和 95 个浏览器用例均通过。构建有既有 bundle 超 500 kB 提示。
- `http://127.0.0.1:8000/api/v1/health` 和 Vite 5173 首页均返回 200；Agent Worker heartbeat 健康。浏览器“重新检查”后恢复为客户 A 已登录，会话消息可见，API 连接显示已连接。`http://127.0.0.1:5173/support` 可供用户继续测试。
- 错误记录：尝试用 Windows `taskkill`/`Start-Process` 做代码热重载后的 Worker 重启被命令策略拒绝，改成按已核实 PID 用 `Stop-Process`，并由长期 exec 会话启动仅两个目标 Worker；API 热重载后一次本机 8000 健康请求超时，随后重启 Uvicorn，健康检查恢复 200。无数据删除/迁移。

## 建议执行范围

| 优先级 | 工作项 | 影响模块 | 验收 |
|---|---|---|---|
| P0 | 埋点并测量三段延迟：Outbox 产生→ConversationEvent 发布、Event 发布→SSE 收到、SSE 收到→相关 UI 查询完成；记录空轮询数、事件数、刷新请求数、断开回收。只记录统计字段，不记正文、token 或完整业务标识。 | `backend/serviceos_api/observability.py`、`worker/runtime.py`、`api/business.py`、`operations.py`；前端 `useConversationEvents.ts`/Playwright 请求计数 | 本地 1/10/50 并发连接的两轮空闲读取、事件 burst 和既有重连场景可复现；报告读取 P50/P95 与空查询量；当前测量不依赖外部 Provider。 |
| P1 | 按 `event.type`/阶段定义缓存失效矩阵；事件到达时即时更新进度回调，短窗口合并重复 query invalidation；只刷新该事件会改变的 messages、Case、UI Document、客服 summaries/tasks/proposals。保留连接失败/重连时全量对账和低频兜底。 | `frontend/src/features/conversation/useConversationEvents.ts`、`ConversationWorkspace.tsx`、现有 query keys 和 Playwright | burst 场景下 GET/POST 数量下降；安全、消息、Evidence、DiagnosticQuestion、协作、Case/Verification 和 UI revision 变化均及时更新；旧/乱序事件不刷新，不丢真实状态。 |
| P2 | 将异步 SSE generator 内同步认证/数据库查询从 ASGI event loop 卸载到受控线程池（或测量证明必要时设计 async 连接）；每次短会话读取后立即释放 Session；明确 disconnect/cancel/error 时清理。 | `backend/serviceos_api/api/business.py`，必要时 `observability.py`；API streaming tests | 多连接慢查询压测时普通 health/read/write 请求不被 SSE DB 查询阻塞；每个客户端断开后无遗留 Session/任务；序号、身份复核和错误响应语义不变。 |
| P3（条件项） | 若基线证明 per-connection 两秒 DB 轮询是延迟/数据库瓶颈，再设计每个 API 进程共享的 PostgreSQL `LISTEN/NOTIFY` 唤醒；payload 只用无敏感内容的会话唤醒键，唤醒后仍从 `conversation_events` 按游标读取。监听重建时先建监听再查询，增加超时/断线兜底轮询。 | `backend/serviceos_api/main.py` lifespan、`api/business.py`、事件发布事务/Outbox、可能的 Postgres 专用测试 | 通知缺失、重复、乱序或 worker/API 重启后，持久序号补取仍不漏事件；API 多实例各自可收到提示；通知不能绕过可见性/租户校验。若压测显示当前方案达标，此项不实施。 |
| P4（验证后另议） | 检查生产 TLS listener 是否需要启用 HTTP/2 以缓解浏览器同源 EventSource 连接槽；仓库当前没有生产部署，先只核实 Nginx 版本/浏览器 ALPN，不把部署上线包含在本次代码实施里。 | `deploy/nginx/production.conf.template`、部署验证 | 同源多标签/多个会话连接数与协议协商验证；不改生产环境，不创建云资源。 |

## 必须保留的约束

- ConversationEvent 持久日志为唯一事实源；通知/内存队列只作唤醒，不直接向客户推送业务正文。
- 客户 PUBLIC、客服 INTERNAL 读取边界、每轮身份复核、Last-Event-ID、本地安全游标和当前授权检查不可削弱。
- 保留 `event-history` 重连恢复；不能把当前“游标在尾部仍恢复当前进度”的行为改成只读取新事件，除非有等价的权威活动快照方案和测试。
- 不以未经测量的延迟数字当作目标；先记录基线，再确认相对改善门槛。
- 本次不引入 WebSocket、Redis、外部托管事件服务或云资源。

## 关键问题

1. 当前事件端到端 P50/P95、最大连接数和 SSE 读查询负载是多少？（需在用户确认后测）
2. 事件类型化刷新是否能在既有所有业务状态路径中安全替代当前通用失效？（实现时用矩阵和集成测试确认）
3. PostgreSQL 通知唤醒是否值得引入？（仅由 P0 基线决定）

## 已做决策

| 决策 | 理由 |
|---|---|
| 先做只读调研和计划，不先改代码 | 用户明确要求确认后再执行 |
| 先测量再决定是否加 NOTIFY/HTTP2 | 当前没有 SSE 负载数据；简单可靠的 durable polling 可能对现有规模更合适 |
| 保留持久事件与 history fallback | 保证通知丢失、重连和权限变更场景可恢复 |
| 暂不引入 PostgreSQL LISTEN/NOTIFY | 本地 50 流压测下事件页读取 P95 约 99ms，且单机测试环境没有数据库饱和证据；生产连接规模未知，应先用新增日志观测 |
| 将浏览器刷新检查放在 Playwright 请求计数中 | 页面查询完成耗时受浏览器/网络影响；测试能确定本次事件 burst 的实际 HTTP 刷新数量，生产端不额外暴露客户端指标 |

## 验收记录

- 1/10/50 流各两轮空闲读取的读取 P50/P95：5.52/15.91ms、17.67/22.24ms、47.34/98.55ms；单轮 wall time 分别约 2.03s、2.11s、2.30s（包含 2s SSE 等待）。50ms 慢读注入下 50 流 event-loop 最大 heartbeat 间隔 66.97ms。
- 5 个连续 `message.created` 事件只让 messages、UI Document、conversations 各发出一次刷新请求；5 个 `agent.progress` 事件没有触发快照 HTTP 请求。
- 完整验证结果：后端 334 passed（2 个既有 PostgreSQL/vector schema warning），前端 92 passed；`check:api`、`build`、`typecheck` 通过。
- 不含 50 流压测的生产容量推断；无生产部署或 ALPN/HTTP2 验证；浏览器事件到 query 完成耗时仍未在真实网络环境采集。

## 遇到的错误

| 错误 | 尝试次数 | 解决方案 |
|---|---:|---|
| PowerShell 正则双引号被误解析为命令 | 1 | 改用 PowerShell 单引号包围 rg 表达式；仅检索命令失败，无源码影响 |
| findings patch 目标包含尚未写入的调研结论 | 1 | 先读取实际 findings 内容，再按现有结构追加 |
| 用 TestClient 读取无限 StreamingResponse 时等待流结束 | 1 | 移除该传输层测试；改为直接驱动真实 response body iterator，并显式 `aclose()` 验证断连回收 |
| 直接调用 FastAPI 路由函数时参数默认值仍是 Query/Header 描述对象 | 1 | 测试显式传入 `after` 和 `last_event_id`，不改路由契约 |
| SSE 生成器测试 chunk 类型为 `str`，断言误按 `bytes` | 1 | 修正为字符串断言；生产代码无影响 |
