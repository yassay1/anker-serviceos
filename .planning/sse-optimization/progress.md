# 进度日志

## 2026-10-17

- 用户要求：基于真实代码链路并参考资料，调研 SSE 优化，先输出计划并等待确认后执行。
- 已读取 `planning-with-files-zh` 技能；建立独立计划目录，不覆盖此前 `.planning/customer-ui-alignment/`。
- 只读核查确认工作树干净；当前分支 `main` 与 `origin/main` 一致。
- 代码链路已核实：Outbox 持久写入→ConversationEvent 递增序号/可见性过滤→REST event-history/SSE 共用 `ConversationService.events`→FastAPI 轮询 StreamingResponse→浏览器原生 EventSource 与本地序号→Query cache invalidation→消息/Case/UI Document 独立 HTTP 刷新。
- 观察点：Outbox idle poll 约 1 秒；每个 SSE 连接约每 2 秒执行一轮 DB 查找且当前 async generator 内同步查询；前端每个事件统一 invalidate 多类活跃 query；事件恢复从 history 起点分页；UI Document 另有 10 秒刷新。以上是代码推导，不是负载/延迟实测。
- 代理现状：SSE 已设置 `proxy_buffering off` 和 3600 秒超时；生产 TLS listener 未配置 HTTP/2，Compose Uvicorn 使用默认单 worker，但仓库尚未部署生产。
- 一手资料已核对并写入 findings：WHATWG/MDN SSE；FastAPI/Starlette StreamingResponse；PostgreSQL 18 LISTEN/NOTIFY；TanStack Query v5 invalidation；NGINX proxy buffering。
- 形成分阶段计划：P0 建基线，P1 事件类型化/合并前端刷新，P2 评估同步 DB I/O 线程池卸载，P3 仅在测量证明需要时引入 PostgreSQL NOTIFY 唤醒，P4 HTTP/2 另行确认。持久 event log 与 history replay 始终保留。
- 用户明确确认按计划执行；当前进入阶段 5/6。
- 前端 `useConversationEvents` 已按后端实际事件 allowlist 建立 invalidation matrix：进度类事件只更新即时内存状态；消息、协作、UI 文档、证据/动作/核验分别失效相关快照；未知事件保留全量 fallback；事件 burst 在 50ms 内合并。open/error 仍立即全量 reconciliation。
- SSE 同步认证/事件页读取改由 Starlette `run_in_threadpool` 执行，单次读取在短生命周期 Session 中完成；每轮继续复核身份与服务层 tenant/visibility 权限。
- 新增安全观测：Outbox 创建到 ConversationEvent 发布延迟；每连接打开/关闭、活跃流计数、轮询/空轮询数、事件数、查询总耗时、最大事件年龄、关闭原因。JSON formatter 用显式字段白名单，不记录事件正文、payload、cookie、租户/会话/用户 ID。
- PostgreSQL 实测回归：1/10/50 并发流各执行 2 次空闲轮询；每连接两次查询，111 个连接均完成关闭清理。事件页读取 P50/P95：1 流 5.52/15.91ms；10 流 17.67/22.24ms；50 流 47.34/98.55ms。50ms 慢读注入下仍维持 event-loop heartbeat（最大间隔 66.97ms）。测试实测为本机单 PostgreSQL 容器和测试数据，不代表生产容量。按当前 2 秒 fallback，空闲查询理论约 0.5 次/秒/流；当前数据不足以支持增加 LISTEN/NOTIFY。
- 完成审计时补充真实路由生成器测试：先写入 PUBLIC、INTERNAL、PUBLIC 事件，再以第一条 PUBLIC 的 `Last-Event-ID` 恢复；实际流返回后续 PUBLIC 序号并略过内部序号空洞，不包含内部消息。断连统计测试直接关闭实际 StreamingResponse iterator，确认清理路径；并发用例 111 条连接最终计数归零。
- Playwright burst 回归实测：5 条 `message.created` 只触发一次 messages、UI Document、conversations HTTP 刷新；5 条 `agent.progress` 只更新状态，不触发快照 HTTP 请求。重复/乱序/非法事件回归仍通过。
- 观测摘要工具已扩展 `operations.metrics`：能聚合 HTTP 延迟、Outbox 到事件发布延迟、每连接平均事件页读取 P50/P95、事件最大年龄、流持续时间、峰值连接数、事件数与空轮询率；新增汇总单测，支持 JSONL 日志回放。
- 后端完整 PostgreSQL 回归 334 passed、2 warnings（既有 pgvector 类型识别和 search_vector computed default 警告）；其后包括新增 Last-Event-ID 路由测试在内的 business API/worker/operations 71 项通过。前端 `check:api`、`build` 均通过，完整浏览器回归 92 passed。最终 `git diff --check` 无 whitespace 错误。
- `.planning/sse-optimization/` 中计划、资料、进度记录已更新为 complete。工作树中无遗留随机测试库；本次不提交/推送。
- 一次初版 TestClient 无限流读取测试被中止并留下唯一临时测试库；已核实为该轮 fixture 的随机 `serviceos_test_36b8...`，清理后数据库列表无残留。替代实现用真实 route 生成器直接采样并关闭；另两次断言错误均只在测试夹具，已修复。
- 本地工作树含此前已存在的 `.planning/customer-ui-alignment/`，保留不触碰；SSE 任务计划目录 `.planning/sse-optimization/` 为本次新增。尚未提交或推送。
- 检索中两次工具调用错误已记录在 task_plan/findings；都是命令引用/patch 目标问题，无代码影响。
- 本轮不进行代码修改。
