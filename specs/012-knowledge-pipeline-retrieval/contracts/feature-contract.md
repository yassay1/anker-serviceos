# 知识入库管道与检索增强 · 功能契约

状态：草案 v1（2026-10-16，用户已确认五项决策：合并切片一次做 / 客服侧上传 / 轻格式先行 / 工具内改写+精排缓办 / 1024 维）。
参照来源：用户旧项目 `D:\Litter\agent\LLMentor\know-engine`（概念移植，非栈移植）；差异与取舍记录于 §8。

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 所属阶段、功能切片 | 后续增量 · specs/012-knowledge-pipeline-retrieval（与 011 同域，扩展 `serviceos_knowledge`） |
| 用户目标与入口 | 客服在 `/desk` 知识面板上传 md/xlsx/csv/jsonl 手册资料；后台管道转换→切片→向量化；Agent 经 `lookup_manual` 混合检索（含可选查询改写）；客户入口不变 |
| 涉及对象及关系 | `KnowledgeDocument` 1—N `KnowledgeDocumentVersion` 1—N `KnowledgeSegment`（父子分段）1—1 `KnowledgeEmbedding`；`KnowledgeJob` 驱动管道。知识层全局（非租户私有），与 Case/Device/Conversation 无外键 |
| 前端 / 后端 / Agent 负责人 | 同一人 |
| 契约状态与版本 | 草案 v1，2026-10-16 |

## 2. HTTP 操作

- `POST /api/v1/knowledge/documents`（multipart：file + 可选 title）
  - 角色：仅 STAFF（SUPPORT/SUPERVISOR/ADMIN）；客户 403。
  - 校验：扩展名/media 白名单 md/txt/xlsx/csv/jsonl；≤10MB；content_hash 去重——同哈希已存在返回既有文档（200 + `deduplicated: true`），不重建管道。
  - 成功 201/200：文档 id、status=`UPLOADED`、version=1；同事务写 `KnowledgeJob`（QUEUED）。
  - 失败：401/403 认证授权、413 超限、415 类型、409 仅用于同文件名不同内容的并发冲突说明（去重走 200）。
- `GET /api/v1/knowledge/documents`（cursor 分页，按 created_at,id）：列表含 status/error_code/version/来源（seed/manual/upload + 上传者标签）。
- `GET /api/v1/knowledge/documents/{id}`：详情 + 分段计数（embedded/pending/failed）。
- 无删除/编辑（撤销与审核工作流明确不做，见 §8）；失败文档可由 SUPERVISOR `POST /api/v1/knowledge/documents/{id}/reprocess` 重新入队（幂等：仅 FAILED/DEAD 状态可重入，否则 409）。
- 实现位置：`api/knowledge.py` + `application/knowledge_pipeline.py`；导出进 `contracts/openapi.json` 与 proposed v1。

## 3. 管道（Ingestion）

- 状态机：`UPLOADED → CONVERTED → CHUNKED → EMBEDDED`；未配置 embedding 时终态 `STORED`（关键词可检索）；任一阶段失败 `FAILED(error_code)`，补偿重试耗尽 → job 死信，文档保持 FAILED 可 reprocess。
- Worker：新角色 `python -m serviceos_api.worker.knowledge`，复用 DB 租约/heartbeat/attempt/死信模式（同 MessageJob），**不引** Redis/XXL-Job/Spring Event；阶段推进在同一租约事务内写状态+事件。
- 转换（轻格式先行）：md/txt 直通；jsonl 行式；xlsx/csv 行式（行不跨块，RAGFlow 式键值对呈现：表头+行→"列: 值"文本）；**不做** PDF/Word/MinerU。
- 切片注册表 `SplitType`：`ROW`（xlsx/csv/jsonl/种子）、`MARKDOWN_HEADER`（md/txt：父分段 skip_embedding=true 只存不嵌，子分段向量化；召回时父标题路径+父文首段扩展）、`LENGTH`（无标题长文兜底，chunk 1200 字 overlap 120）。
- 向量化：复用 011 `EmbeddingAdapter`（1024 维）；批 10 条、按批提交可续跑；未配置 → `STORED`。
- 种子/手册：`knowledge_ingest` CLI 改为写入 documents（source_kind=seed_corpus/manual）+ segments，entry_key 与自然键语义不变；重跑幂等。
- 上传内容标签：source_kind=upload 的分段 curation.label="客服上传资料，未经独立审核，仅作内部参考"；检索输出 NOTE 携带。

## 4. 检索增强（lookup_manual 内部）

- 查询改写 `QueryRewriter`（httpx，同 embedding 显式外发边界）：仅当 `llm_configured` 且开关开启；策略=型号/错误码提取 + 纠错 + 中英关键词互译；输出 JSON 解析失败/超时/非 200 → **回退原 query**（fail-closed，不伪造改写）。
  - 安全边界：改写提取的型号**只用于关键词加权与向量查询文本**，绝不放宽 VERIFIED 设备门控（门控仍只看 Device Passport）。
- 父分段扩展：子分段命中时摘录含父标题路径与父文首段（≤现有 1600 字上限内）。
- 引用审计：检索引用（entry_key、source_ref、sha16、路径 keyword/vector/fused、是否改写）写入 `AgentRun.result_payload["knowledge_references"]`（INTERNAL，不进公开消息/SSE）。
- 阶段 progress：`retrieval_rewrite`（仅实际发生时）/`retrieval_keyword`/`retrieval_vector`/`retrieval_fused`，固定 payload 不含 query 文本。
- RRF k=60 不变；**精排缓办**（875→数千条规模 RRF+门控足够；router 未开 embedding 白名单前无精排依赖）。

## 5. 事件与投影

- 新 outbox 事件仅 INTERNAL：`knowledge.document_updated`（document_id/status/version），供 /desk 面板轮询/未来 SSE；不发 PUBLIC。
- /desk 知识面板：上传按钮 + 文档列表（status 徽章、error_code、来源标签）+ reprocess 按钮（SUPERVISOR/ADMIN）；状态经 GET 列表轮询刷新，不用假进度。

## 6. 验收

| 路径 | 预期 | 证据 |
|---|---|---|
| 上传成功 | 201 + job 入队；worker 推进 UPLOADED→CONVERTED→CHUNKED→(EMBEDDED/STORED)；分段数>0 | test_knowledge_pipeline.py（--require-postgres） |
| 去重 | 同字节二次上传 200 deduplicated，无新 version/job | 同上 |
| 权限 | 客户 403；未登录 401；reprocess 非 SUPERVISOR 403 | 同上 + live |
| 类型/大小 | 415/413 稳定错误码 | 同上 |
| 失败与补偿 | 损坏 xlsx → CONVERTED 失败 FAILED(error_code)；attempt 耗尽死信；reprocess 重新入队成功 | 同上 |
| 切片 | md 父子分段：父 skip_embedding、子有向量；xlsx 行不跨块 | 同上 |
| 检索 | 父子扩展摘录含父标题；references 写入 run payload；progress 四阶段真实 | 同上 + chain 冒烟 |
| 改写降级 | 假 transport 500/超时/坏 JSON → 原 query 结果不变；门控不被改写突破（提取型号≠VERIFIED 仍 0 命中） | 同上 |
| 回归 | 011 全部测试 + 226 基线保持绿；openapi/sync/compose 检查通过 | 命令记录 |

## 7. 明确不包含

PDF/Word/MinerU/Tika、ONNX/Provider 精排、Text2SQL/Text2Cypher、知识审核工作流与删除、租户私有知识库、brother-chunk 扩展、ES/Neo4j/Redis/XXL-Job、客户侧上传知识、SSE 推送文档状态（先轮询）。

## 8. 与 know-engine 的差异（取舍记录）

| know-engine | 本项目 | 原因 |
|---|---|---|
| ES KNN+全文+混合 | pgvector + 进程内关键词打分 | 架构基线 Postgres-only |
| Spring Event + Redis 锁 + XXL-Job | DB 租约 worker + 同事务状态推进 | 既有 worker 模式，零新增中间件 |
| Text2SQL/TableMeta 路由 | 类型化工具（后续 014 切片） | 宪章：Agent 不经任意 SQL；工具经应用服务 |
| BGE ONNX 本地精排 | 缓办 | 新增模型运行时依赖，规模不需要 |
| 意图识别→Prompt 路由 | Agent 工具自选 + Skill eligibility | Agent loop 已承担路由，避免重复 LLM 跳 |
| MinerU/Word→MD | 轻格式先行 | 转换依赖与运维成本，后续切片 |
| 父分段存 Redis | 父分段同表 skip_embedding | 单库原则 |

## 9. 变更与落地记录

- 决策确认：2026-10-16（合并切片/客服上传/轻格式/工具内改写+精排缓办/1024 维）。
- 实现日期：2026-10-16。实际变更文件：
  - 后端新增：`application/knowledge_splitter.py`、`application/knowledge_pipeline.py`、`application/query_rewrite.py`、`api/knowledge.py`、`worker/knowledge.py`
  - 后端重写（011 未上线，直接修订）：`migrations/versions/0015_knowledge_retrieval.py`（documents/versions/segments/embeddings/jobs 五表）、`persistence/knowledge_models.py`、`knowledge_ingest.py`（种子→documents+segments）、`application/knowledge_retrieval.py`（segments+父分段扩展+引用+阶段）
  - 后端修改：`application/agent_services.py`（改写+引用写回+PROGRESS_STEPS 四阶段）、`integrations/embedding_adapter.py` 与 `application/query_rewrite.py`（httpx.Client 修复模块级 post 不支持 transport 的缺陷）、`worker/health.py`（knowledge 角色）、`main.py`、`application/contracts.py`、`pyproject.toml`/`uv.lock`（openpyxl）
  - 前端：`api/client.ts`（3 个 helper）、`features/overview/KnowledgePanel.tsx`、`DeskOverview.tsx` 挂载、`app/queryKeys.ts`、`styles/workspace.css`
  - 基础设施：`compose.yaml`/`compose.production.yaml`（knowledge worker+healthcheck）、`README.md`、`docs/operations.md`
  - 测试：`tests/test_knowledge_retrieval.py`（12 个，含 MockTransport 适配器测试）、`tests/test_knowledge_pipeline.py`（5 个）、`tests/test_database.py` 期望表集更新
- 本地命令与结果（2026-10-16，Windows，一次性 `pgvector/pgvector:pg17` @55433）：
  - `pytest backend/tests --require-postgres` → **234 passed**
  - `export_openapi --check`、`sync_implemented.py --check`、三个 `docker compose config -q` → 通过
  - 管道冒烟：md 上传→worker→STORED+父子分段+INTERNAL 事件；csv 行 KV 分段；坏 xlsx→FAILED+死信+SUPERVISOR reprocess；去重/403/415/413 均按契约
  - 真实链路（qwen-max）：run COMPLETED；`knowledge_references` 3 条（qa-v1:robovac:r4/r208/r27，path=keyword）；progress 阶段 worker_started→lookup_started→retrieval_keyword→retrieval_fused→lookup_completed→worker_completed；最终答复正确引用 E28 丢地图手册内容
  - 真实链路（qwen-max + qwen3-vl-embedding）：run 完成；`knowledge_references` 含 keyword/vector/fused 混合路径（中文 query 经 vector 命中英文语料）；progress 阶段 worker_started→lookup_started→retrieval_rewrite→retrieval_keyword→retrieval_vector→retrieval_fused→lookup_completed 真实落库；最终答复正确引用 E28 丢地图手册
  - 查询改写实测：中文 query → applied=True，追加英文关键词（map loss/loses map…）与型号 E28；provider 故障/解析失败/超时回退原 query（fail-closed 有测试）
  - 合并同步：2026-10-16 fast-forward 至 origin/main 0e5e07a（PR#16）；上游 `1c7da43` 已官方修复 CRLF 指标解析，本切片移除自己的重复正则改动，以上游 normalize 为准
- 已知复现问题（既有、非本切片）：router 版 qwen-max 首轮偶发 reasoning 耗尽 `max_completion_tokens=1000` 导致 content 空 → `agent_final_response_empty`；worker 重试/checkpoint 恢复路径可自愈（已实测）。runtime 预算修订待用户批准为独立切片。
- 已知限制：embedding 凭据已配置于本地 `backend/.env`（gitignore），**不得提交**；精排、PDF/Word、审核工作流、brother 扩展明确不做（§7）；上传资料未经独立审核，仅带标签进入检索。
- 对 `docs/development-plan.md` 勾选的影响：无（后续增量，不改阶段验收状态）。
