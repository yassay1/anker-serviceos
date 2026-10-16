# 工具信封、014 只读工具与检索硬化 · 功能契约

状态：草案 v1（2026-10-16）。用户决策：curated 种子+上传双通道 / **上传不 gate 不带标签、成功即入库** / 关键词预过滤+复算 / get_case_stage 阶段投影。

## 1. 统一工具信封

- `ToolResult`：`status ∈ {OK, NOT_FOUND, DEGRADED, REJECTED, RECORDED, LOADED}`、`items[]`、`references[]`、`applicability`、`notes[]`、`payload?`。
- 全部 Agent 工具（lookup_manual、query_order_warranty、check_dealer_authorization、get_case_stage、load_skill、request_missing_evidence、propose_action）产出信封；给模型的字符串由序列化器生成，**字节兼容现有 prompt 契约**（"SOURCE:" 头等断言保持绿）。
- 信封写入 `AgentRun.result_payload["tool_envelopes"]`（INTERNAL 审计/评测）。
- 验收：测试断言每个工具返回同一信封 schema。

## 2. 分叉可见与 legacy 删除

- `result_payload["retrieval_path"] = "corpus"`（legacy 删除后恒定，字段保留一个切片供评测对齐后移除）。
- readiness 增 knowledge 块：corpus_present/segments/embedded/provider/vector_enabled。
- conftest 会话级自动 ingest 种子 → 测试语料常备；删除 `_lookup_manual_files`；语料空时 lookup 返回类型化"语料未导入"而非文件扫描。
- 验收：health/readiness 显示 corpus 状态；legacy 代码删除；基线全绿。

## 3. 014 只读工具与种子

- 改名：lookup_order→`query_order_warranty`、match_dealer→`check_dealer_authorization`（语义/三态/别名不变）；新增 `get_case_stage`：阶段投影 INTAKE/DIAGNOSIS/ACTION_PENDING_APPROVAL/ACTION_EXECUTING/VERIFICATION/RESOLVED/CLOSED + waiting_on（客户/审批/回执/核验）。
- 新 curated 种子：`orders-v1.jsonl`（24 行订单 facet）、`dealers-v1.jsonl`（336 行经销商 facet），来源标注同 qa-v1；ingest 双通道（种子+上传）不变。
- "查不到"= 类型化 NOT_FOUND 信封，非异常。
- 验收：shipping 意图工具级回放（客诉表 Shipping inquiry 行带订单号 → 质保结论；经销商行 → 授权结论）。

## 4. 单一检索实现与上传策略

- 新增 staff-only `GET /api/v1/knowledge/search?q=` 与 `GET /api/v1/knowledge/stats`，复用同一 `KnowledgeRetrieval.search`（gate 参数区分 Agent 门控/客服浏览）；全仓禁止第二检索实现。
- **上传成功即入库可检索，不加审核门、不加"未审核"标签**（用户决策）；curation 仅保留 source_kind/source_ref 溯源字段。
- 验收：grep 检索实现唯一；stats/搜索端点测试。

## 5. 检索下沉 SQL

- 0015 增：`search_vector tsvector` generated（title||content, 'simple'）+ GIN；`pg_trgm` 扩展 + content GIN；`models` jsonb GIN；jobs(status, available_at) 索引；embedding **hnsw**（凭据已落地）。
- 关键词路：SQL 预过滤（tsvector @@ plainto_tsquery OR CJK run LIKE/trgm）→ Python 复算打分（保 CJK 行为）。
- 验收：合成 1 万 segments，P95 不随 N 线性增长（记录实测数）。

## 6. 向量腿可见性

- 已点亮（DashScope 直连）；readiness/stats/面板展示 vector_enabled 与 embedded/total 覆盖率，keyword-only 为可见事实。

## 7. 改名不改契约

- lookup_manual 名字保留；docstring 更新为"检索已批准手册 + curated 语料 + 客服上传资料"；skills.py allowed_tools 同步说明。

## 8. 明确不包含

审核工作流（用户否决）、Text2SQL、客户上传进全局库、Agent 级 shipping 回放（归评测切片）、面板检索 UI（先 endpoint，UI 后续）。

## 9. 落地记录

- 实现日期：2026-10-16。变更：`application/tool_envelope.py` 新增；`agent_services.py` 全工具信封化 + 改名 query_order_warranty/check_dealer_authorization + 新增 case_stage + legacy 文件扫描删除 + settings 注入；`agents/runtime.py` 工具接线/docstring/settings 传递；`knowledge_retrieval.py` gate 参数 + tsvector/trgm SQL 预过滤；`knowledge_ingest.py` orders-v1/dealers-v1 种子；`api/health.py` readiness knowledge 块；`api/knowledge.py` search/stats 路由；0015 增 search_vector generated + GIN/trgm/models/jobs/hnsw 索引与 pg_trgm；conftest 会话级自动播种；上传按用户决策去标签去 gate。
- 验证（2026-10-16）：`pytest --require-postgres` **246 passed**；openapi/sync/check:api/typecheck/build 全绿；dev 库 6 文档/1235 分段/1235 向量（qwen3-vl-embedding）；readiness `knowledge=ready, vector=on`；staff `/knowledge/search` "订单 质保 承运商" → fused 命中订单行；customer 403；活体 Agent 此前已验证质保/授权判定（含"德国"别名）。
- 已知限制：Agent 级 shipping 回放归评测切片；面板搜索 UI 未做（先 endpoint）；1 万级 P95 基准未实测（索引已就位）。
