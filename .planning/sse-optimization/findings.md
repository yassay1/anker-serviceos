# SSE 链路与资料调研发现

> 外部资料和网页摘要只记在此文件；按不可信信息处理，只提取与当前实现相关的技术事实。

## 当前代码链路

- `ConversationService.record_event` 写入 Outbox；`dispatch_outbox_event` 校验公开事件 allowlist、事件 payload、当前协作模式与 `reply_policy`，再生成带 conversation 内递增 `sequence` 的 `ConversationEvent`。事件由业务事务/Outbox 工作流持久化，而不是 SSE 进程内临时广播。
- `ConversationService.events` 用 `(tenant_id, conversation_id, sequence > after)` 读事件；客户只读 `PUBLIC`，客服可读当前授权范围内事件。REST event-history 和 SSE 共用该读取服务。
- `GET /conversations/{id}/events` 使用 FastAPI `StreamingResponse`。游标取 `max(after, Last-Event-ID)`；连接期间每轮重新验证 cookie 身份、最多读取 100 条，空批次发送 SSE 注释 keepalive 后等待 2 秒。发送字段是 `id: sequence` 与 JSON `data`；响应带 `text/event-stream`、`Cache-Control: no-store`、`X-Accel-Buffering: no`。
- Outbox Dispatcher 使用通用 worker loop；无事件时约每 1 秒再次轮询。按当前实现，单看两个轮询等待理论上可能叠加出约 0–3 秒量级的事件可见等待，但实际 P50/P95 还受队列、请求和网络影响，未采集，不能称为实测延迟。
- API SSE 循环对每个连接每约 2 秒独立运行一条持久事件查询；空闲连接开销随连接数线性增长（按代码推导约 0.5 次查询/秒/连接，非实测）。数据库当前是同步 psycopg/SQLAlchemy engine，线程池/连接池配置未专项调优。
- 前端 `useConversationEvents` 从 `localStorage` 读已保存游标，连接浏览器原生 `EventSource`，接收后校验会话、序号、可见性和事件内容并保存游标；`onerror` 依赖浏览器 EventSource 原生重连/Last-Event-ID。新连接会做 event-history 补取，补取只恢复进度/专家活动状态。
- `refreshSnapshots` 会失效 messages、conversations、相关 Case 缓存和 UI Document 缓存；客服端还失效 tasks/proposals/summaries。它目前在连接打开、错误和每一条有效 SSE 事件后直接触发；值得评估事件突发时的重复失效/refetch。连接打开/错误也立即 refresh。
- `ConversationWorkspace` 对活动会话读取 UI Document 时调用 POST `/ui-document/refresh`，同时还配置 10 秒 `refetchInterval`。SSE 每条事件又会失效此 query。后端以 `context_signature` 判定内容无变化时直接返回 active document，不重复创建 revision/事件；不过每 10 秒仍会重跑投影查询，写成本需与单纯读快照区分。
- Nginx 的 `deploy/nginx/proxy.conf` 已设置 `proxy_buffering off`、`proxy_read_timeout 3600s` 和 HTTP/1.1；不能把默认代理缓冲假设成此项目当前已存在的瓶颈。
- 目前有通用 HTTP 请求耗时日志，但未发现 SSE 活跃连接数、每连接事件查询次数、Outbox 到 ConversationEvent 延迟、事件到浏览器/刷新完成延迟等指标。长流耗时是否被通用 HTTP middleware 准确覆盖需专项验证，不能直接拿它当 SSE 会话时长指标。
- 现有测试已有重连/补取/乱序/隐私/静默恢复等大量边界保护；优化计划应增加 SSE 端到端延迟、连接/查询负载、refresh fan-out 的基线和回归比较，不应移除当前恢复路径。
- 动态 UI 文档是另一条按需 HTTP 查询/刷新链路；SSE 只在前端触发缓存失效，不携带 UIDocument 组件树。消息正文/富回复和 UI Document 的持久业务来源各自独立。
- 现有测试覆盖 event-history 序号回放、PUBLIC/INTERNAL 权限、非法游标、重复/乱序/断线重连、分页补取不覆盖新进度、会话切换时忽略迟到事件、存储异常和 SSE 静默时对账；计划应扩充定量时延/负载观测，而非重复已有边界用例。

## 权威资料

- WHATWG HTML Living Standard, [Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)：浏览器原生 EventSource 在重连时发送 `Last-Event-ID`；支持服务端 `retry` 时间字段；冒号注释是心跳方式，规范建议为兼容短 idle timeout 的代理“约 15 秒左右”发送注释。当前实现用持久序号游标，未设置 `retry:`，每 2 秒空轮询发送注释。
- MDN, [Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) / [EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)：EventSource 持有长连接并自动重连；部署使用 HTTP/1.1 时，浏览器/域名跨标签页的并发 SSE 连接数有限（MDN 提醒常见浏览器限制约 6）；HTTP/2 会协商并发流数。应核对面向浏览器的真实协议和多标签页连接数再判断是否是当前约束。
- FastAPI, [Stream Data](https://fastapi.tiangolo.com/advanced/stream-data/) 与 [Custom Response: StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/)：StreamingResponse 按 yield 逐块传输；无限生成器需要可取消的异步等待点。当前流有 `await asyncio.sleep(2)`，但需在测试中确认断连退出与资源释放。
- NGINX, [ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)：默认 response buffering 可缓冲代理响应；禁用后收到的数据会同步转发；`X-Accel-Buffering: no` 可关闭缓冲；`proxy_read_timeout` 是上游两次读取之间的超时。项目当前配置已经针对 SSE 关闭缓冲并设置长读取超时。
- PostgreSQL 18 官方资料：[LISTEN](https://www.postgresql.org/docs/current/sql-listen.html) 有初始订阅竞态，建议先提交 LISTEN，再查状态，之后依赖通知；[NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html) 仅在事务提交后送达，重复的同 payload 通知可合并，默认 payload 小于 8000 bytes。因此若启用通知，只传“检查事件表”的唤醒提示；真实事件仍从 `conversation_events` 读取，监听建立/断线时补查，不传用户正文。
- TanStack Query v5 官方资料：[QueryClient.invalidateQueries](https://tanstack.com/query/latest/docs/framework/react/reference/classes/QueryClient)：默认会重新拉取匹配的活跃 query；所以当前每个事件统一失效多个 key 不只是本地标记，可能形成真实 HTTP/数据库负载。建议按事件类型建立失效矩阵，并用回归测试证明不漏刷新。
- Starlette 官方 `StreamingResponse` API/实现：[Responses](https://www.starlette.io/responses/)、[pinned implementation source](https://github.com/Kludex/starlette/blob/main/starlette/responses.py)：异步 iterable 由 event loop 逐项 await；同步 iterable 由 `iterate_in_threadpool`/AnyIO 线程池取值。当前 async generator 内的同步 SQL 调用不是这种自动卸载路径，若改成 sync generator则不能直接 await `request.is_disconnected()`，需要设计和验证取消/断连行为，或只将读页辅助函数显式卸载到线程池。

## 对当前优化方向的初步结论

- 可靠性基线已经不错：持久 Outbox→ConversationEvent 顺序日志、可见性过滤、历史补取、Last-Event-ID、浏览器游标校验、网络异常刷新；没有必要为“实时”重写成 WebSocket。
- 先测量两处等待和 fan-out：Outbox 空轮询 1 秒，API 每流空查询/心跳 2 秒；每事件前端统一失效多组 query，且客服/客户 UI 文档可能触发多次投影读取。
- 候选优化应条件化：前端对事件按类型选择失效 query，并短窗合并同一批事件的刷新；服务端 SSE 由每连接轮询探索改成进程级 PostgreSQL LISTEN/NOTIFY 唤醒 + 持久事件表查询兜底（仅在连接规模/DB 负载证明瓶颈后设计）；降低全历史 replay 的成本，需提供等价的权威“最新活动状态”恢复语义。
- 不建议直接缩短轮询间隔、丢弃 event-history、使用只存在进程内的广播、或直接引入 Redis；这些会增加数据库负担、破坏重连恢复或引入部署成本，除非数据证明收益和必要性。
- 候选实现顺序宜先做事件类型→query invalidation 矩阵与短时合并，并用事件链路跟踪验证不漏 UI 更新；再对比通知型唤醒方案。保留低频完整对账作为防丢失通道。
- SSE endpoint 是 `async` generator，但生成器内部直接运行同步 psycopg/SQLAlchemy Session 查询和同步认证查询；这类 I/O 会占用 ASGI 事件循环。高并发时是需要量化的调度阻塞风险。候选方案优先评估将短数据库读取段卸载到 AnyIO/Starlette worker thread，或等价 async DB；先验证负载与事件循环延迟，不切换全套 async ORM。
- 生产 Nginx TLS listener 当前配置未看到 HTTP/2 开启指令；浏览器 SSE 使用 HTTP/1.1 时，多标签页/同域并行可能受 EventSource 连接槽限制。需确认实际部署 Nginx 版本和 TLS ALPN，再判断是否把 HTTP/2 纳入范围。
- `compose.production.yaml` 的 Uvicorn 命令没有配置 worker 数，按默认单 worker 运行；若实际部署沿用该配置，同一 API 事件循环中的同步 SSE DB 查询会影响同 worker 其他请求的调度。此配置观察不等同于当前生产部署状态（仓库明确未部署）。
- 前端 event-history 恢复从 `after=0` 开始，按 100 条分页读到最新，即便 localStorage 的 EventSource 游标已经在尾部；这是为了恢复页面重载后的当前 Agent/专家活动 UI，但事件日志增长时重连补取成本随会话历史变长。当前测试专门要求“游标已在尾部仍恢复最新进度”，不能简单改成只读取新游标之后。

## 实施后本地基线（2026-10-17）

- 在一次性 Alembic 测试库上，用真实 `stream_events` StreamingResponse 生成器和真实 PostgreSQL 事件查询，分别并发打开 1、10、50 个安静连接；每连接执行初始空查和 2 秒后的第二次空查，再显式关闭生成器。共 111 个连接，全部记录 2 次空查询，最后 active stream 计数为 0。
- 事件页读取 P50/P95：1 流 5.52/15.91ms；10 流 17.67/22.24ms；50 流 47.34/98.55ms。50 流一次两轮约 2.30 秒（含规范 2 秒等待、生成器/线程池调度）。额外把 poll helper 加 50ms 同步延迟，50 流 event-loop heartbeat 最大间隔 66.97ms；表明慢同步 DB 路径没有直接阻塞 ASGI loop。以上只代表本地回归环境，不是生产容量承诺。
- 按 SSE 两秒空闲读取配置估算，空闲轮询负载为 0.5 次查询/秒/连接；50 流约 25 次/秒。当前样本没有显示应为此加入 PostgreSQL NOTIFY：需要真实生产连接数和 DB 负载达到瓶颈后再决策。
- Playwright 受控 HTTP 测量：5 个 `message.created` burst 在 50ms 合并窗内触发 messages、UI Document、conversations 各 1 次刷新；5 个进度事件触发 0 次快照请求。已有连接错误和重连仍全量刷新。
- 当前后端 SSE 关闭日志的读取时间是每连接累计值；本地压测的 P50/P95 由测试夹具采样，生产日志未内置 histogram/p50/p95 聚合。`outbox_delay_ms` 和事件年龄可供未来按日志窗口做统计。

## 待确认假设 / 风险

- 需要查明 Outbox dispatch 的调用频率/持久化时机，确认目前两秒数据库轮询是否是主可见延迟来源。
- 缓存失效触发 UI Document 刷新时会调用 POST `/ui-document/refresh`（读取界面可能包含持久化/版本副作用）；需评估每条事件都失效是否导致不必要的新 revision 和数据库写入。
- SSE generator 的每个客户端轮询都会开数据库 Session 并执行事件查询；实际规模、连接数、DB pool 和空轮询成本尚无指标，不先预设需要 Redis/新消息基础设施。
- 异步/流式协议改动需保留租户和可见性过滤、Last-Event-ID、history 补取、幂等 sequence、代理缓冲关闭和当前认证失效语义。
- 工具检索命令有一次 PowerShell 引号解析错误（正则双引号被 shell 当作表达式）；改用正确 quoting 后重试，不代表代码故障。

## 2026-10-17 回复等待与呈现续查

- 用户在实际会话等待近一分钟以上没有回复。只看 API health/readiness 的 200/ready 不代表 Agent Worker 在线；开发启动器通过 `SERVICEOS_START_AGENT=1` 显式 opt-in 才启动主 Agent Worker，且缺少模型凭证时不会启动。该变量若永久打开会导致后续客户消息调用外部模型并可能产生费用，不应擅自改写 `.env`。
- 实际本地排查发现 API、inspection/actions/followups/outbox workers 在运行，但 `serviceos_api.worker.main` Agent Worker 缺失；该消息的 `MessageJob` 曾长时间 QUEUED（attempts=0），没有 AgentRun。故本次长等待根因是未消费队列，而非 SSE 传输或模型推理耗时。
- 为响应用户这条明确提交的待处理消息，临时启动了 Agent Worker；启动后该 AgentRun 从 `2026-10-17T04:26:49.820613Z` 至回复消息创建 `2026-10-17T04:26:57.054700Z`，约 7.2 秒。该单例不代表模型整体性能分布。
- Worker 从仓库根目录以 `uv run --project backend --locked python -m serviceos_api.worker.main` 启动，避免从 `backend/` 运行时将 `.env` 中相对的 embedding API key 文件路径解析错。先前 cwd 错误造成一次 worker 启动失败，无业务写入。
- 当前 Worker 取得完整 `AgentResult` 后，经 `ConversationService.publish_agent_response` 做授权/安全检查并持久化整条消息；现有 SSE 只流送生命周期/进度事件，`message.created` 到达后前端 refetch 整条消息。尚无 token/delta 生成协议。
- 安全约束：不能把未经过后端发布授权和内容检查的模型原始 token 逐字发给客户。要呈现生成过程，须在最终正文通过安全发布门后，通过受授权持久事件传输其分片；这提升“看到已批准答复”的呈现体验，不缩短模型实际生成/安全校验时间，不能描述成真实 token 首字节。
- 工作树有既有未提交变更：`git diff --stat` 为 40 个前端文件、550 insertions/1265 deletions，包含用户先前要求回退客服 UI 的修改以及可能的其他修改；继续修改前必须对具体目标文件逐项核实并保留既有内容。不要把这些改动归因给本轮。
