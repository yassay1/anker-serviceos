# 混合知识检索（pgvector + 关键词） · 功能契约

状态：草案（契约先行）；本切片为后端/Agent 内部改造，无新增 HTTP 路由，`contracts/openapi.json` 不变化。

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 所属阶段、功能切片 | 后续增量 · specs/011-hybrid-knowledge-retrieval |
| 用户目标与入口 | `/support` 用户提问后，Agent 经 `lookup_manual` 工具检索已 curation 的售后知识（本地手册 + 赛题 Q&A 语料），回答带来源、版本与适用性标注；`/desk` 无界面变化 |
| 涉及对象及关系 | 不新增业务对象。知识库是全局只读资料层（独立 `serviceos_knowledge` schema），不属于 Case/Device/Conversation；检索结果只是 Agent 上下文输入，不写设备事实 |
| 前端负责人 / 后端负责人 / Agent 负责人 | 不涉及 / 同一人 / 同一人 |
| 集成负责人 | 同一人 |
| 契约状态与版本 | 草案 v1，2026-10-16 |

## 2. 范围与决策记录（用户已确认）

1. 向量存储：同 PostgreSQL 17 实例 + pgvector 扩展，独立 `serviceos_knowledge` schema；不引入独立向量数据库服务。本地/CI 镜像改为 `pgvector/pgvector:pg17`（数据卷兼容）；生产 RDS 需启用 `vector` 扩展。
2. Embedding：阿里云百炼 DashScope OpenAI 兼容模式（默认 `text-embedding-v4`，1024 维）。新增 `SERVICEOS_EMBEDDING_MODEL/BASE_URL/API_KEY/DIMENSIONS`；未配置凭据时**不造假向量**，向量路径关闭。
3. 语料：全量自动 ingestion，仅收 `Status=Published` 且 `Consumer Visible=Visible`（扫地机 593 + 吸奶器 279 = 872 条；3 条 Invisible 排除）。来源为 `data/reference/hackathon/` 赛题工作簿，经脚本转换为 committed 的 curated 种子 `backend/serviceos_api/knowledge/corpus/qa-v1.jsonl`（含工作簿 sha256、sheet、行号、PN/PDT、目录、"赛题参考数据，非已核验厂商政策"标注）。240 条客诉工单不入检索库，留作后续评测集切片。
   2026-10-16 上游 `0438551` 重导出工作簿（sha `0279f939…`）：行级 diff 确认 Q&A 内容与旧导出 `0cc02e65…` 完全一致（872/872、各 sheet 维度不变），语料已重绑新 sha 并重建向量，条目与检索行为不变。
4. 现有 3 份 md 手册同时入库（source_kind=manual），保持既有 APPLICABILITY 标签（A1229/T8D04/generic）；md 文件仍是内容真源。
5. 工作流：沿用仓库 speckit 约定，不引入 OpenSpec 第二套规范。

## 3. HTTP 操作

无新增或变更路由；ingestion 与向量化是显式本地/运维命令：

- `python -m serviceos_api.knowledge_ingest`：幂等 upsert 种子语料与手册；按 `entry_key` 唯一；内容变化时重置对应 embedding；删除不在当前种子中的旧条目。无 Provider 也可运行（仅关键词检索可用）。
- `python -m serviceos_api.knowledge_ingest --embed`：额外调用配置的 Embedding Provider 生成/回填向量；未配置时非零退出（fail closed），网络失败中止并允许重跑（已完成批次保留）。
- API/Worker 启动不自动建 schema、不自动 ingest（与迁移/Checkpoint 显式初始化约定一致）。

## 4. 检索行为（`lookup_manual` 内部升级，工具契约不变）

- 降级链：`serviceos_knowledge` 语料为空 → 现有文件扫描逻辑原样保留（现有测试不破）；语料存在但 Embedding 未配置或调用失败 → 本次调用降级纯关键词，不失败、不伪造向量结果。
- 关键词路径：进程内对全部条目做 token 重叠打分（复用 `_search_tokens`，含 CJK 二元组），标题权重高于正文；每条最多选 4 个命中段落。
- 向量路径：查询文本 → Embedding Provider → pgvector 余弦距离 top-N（仅带向量且过门控的条目）。
- 融合：RRF（k=60），取 top 3；输出保持 `SOURCE | VERSION sha256 | APPLICABILITY` + 摘录 + 现有头尾免责声明与 5000 字符上限；progress 事件仍为 `lookup_started`/`lookup_completed`，查询文本不入日志与 progress payload。
- 型号门控：条目 `models`（PN 列表）非空时，要求与已 VERIFIED 设备型号（casefold）有交集才可召回；`models` 为空视为通用资料。门控在关键词与向量两条路径前统一执行。
- 隐私边界：查询文本会发送给已显式配置的 Embedding Provider（与 LLM 调用同一信任边界，base URL 显式配置防止隐式外发）；语料本身不含客户数据。

## 5. 数据与迁移

- 迁移 `0015_knowledge_retrieval`：`CREATE EXTENSION IF NOT EXISTS vector`；`CREATE SCHEMA IF NOT EXISTS serviceos_knowledge`；表 `knowledge_entries`（entry_key 唯一、source_kind、source_ref、source_sha256、corpus_version、title、content、directories JSONB、models JSONB、pdt、status/visibility、applicability、时间戳）与 `knowledge_embeddings`（entry_id PK/FK cascade、model、dimensions、embedding vector(1024)、embedded_at）。
- `backend/migrations/env.py` 的 schema 过滤扩展为业务 + knowledge 两个 schema；knowledge 表纳入同一 metadata，避免 autogenerate 漂移。
- 维度固定 1024：配置维度不等于 1024 时 ingestion fail closed（更换维度需新迁移）。
- 生产 RDS：`vector` 扩展需具备权限的角色预先启用；运维手册补充说明。

## 6. 事件、异步与投影

- 不涉及新事件/SSE/UI Schema。ingestion 是运维命令，不进 Outbox。
- Worker 主进程行为不变；`lookup_manual` 内新增一次 embedding API 调用（有凭据时），超时沿用 `SERVICEOS_LLM_TIMEOUT_SECONDS` 同类边界（独立 `SERVICEOS_EMBEDDING_TIMEOUT_SECONDS`，默认 30s，上限 120s）。

## 7. 验收

| 路径 | 预期 | 证据 |
|---|---|---|
| 迁移与 ingestion | PostgreSQL 上 upgrade head 成功；ingest 幂等重跑不重复、内容变更重置向量、种子外条目清除 | test_knowledge_retrieval.py（--require-postgres） |
| 关键词检索与门控 | 无 Provider 时命中 Q&A/手册；PN 门控：未核验型号不召回 T2352 等专属条目，核验后召回 | 同上 |
| 混合融合 | 假 Embedding adapter 下向量路径参与 RRF 排序并可改变 top3 | 同上 |
| 降级 | 语料空→文件扫描旧行为（现有 test_worker_runtime/test_skills 保持绿）；embedding 调用抛错→关键词结果正常返回 | 现有回归 + 新测试 |
| fail closed | `--embed` 无凭据非零退出；维度≠1024 拒绝 | 新测试 |
| 工具契约 | lookup_manual 输出仍含 SOURCE/VERSION/APPLICABILITY 与免责头尾，≤5000 字符；progress 两步不变 | 现有 + 新测试 |
| 基础设施 | compose/CI/deploy 默认镜像 pgvector/pgvector:pg17；容器冒烟通过 | ci.yml 实际运行 |
| 真实 Provider | DashScope 凭据下 embedding 生成与多轮检索质量 | **待用户提供凭据后执行，先标未测** |

## 8. 明确不包含

独立向量数据库、语义缓存、rerank 模型、240 条客诉评测基准集（后续切片）、经销商/订单结构化查询工具（后续切片）、前端界面、Q&A 内容的人工逐条复审（以 Published+Visible 过滤 + 来源标注代替，条目级纠错走后续 curation 迭代）。

## 9. 变更与落地记录

- 契约确认者和日期：用户于 2026-10-16 确认四项关键决策（工作流/存储/Provider/入库范围）。
- 实现日期：2026-10-16。实际变更文件：
  - 新增：`backend/migrations/versions/0015_knowledge_retrieval.py`、`backend/serviceos_api/persistence/knowledge_models.py`、`backend/serviceos_api/integrations/embedding_adapter.py`、`backend/serviceos_api/application/knowledge_retrieval.py`、`backend/serviceos_api/knowledge_ingest.py`、`backend/serviceos_api/knowledge/corpus/qa-v1.jsonl`（872 条）+ `corpus/README.md`、`backend/tests/test_knowledge_retrieval.py`
  - 修改：`backend/migrations/env.py`（双 schema 过滤）、`backend/serviceos_api/settings.py`（EMBEDDING 配置+校验）、`backend/serviceos_api/application/agent_services.py`（lookup_manual 混合路径+legacy 降级原样保留）、`backend/pyproject.toml`（httpx 主依赖、corpus package-data）、`backend/uv.lock`、`compose.yaml`/`compose.production.yaml`/`deploy/compose.test.yaml`（pgvector 镜像默认值、agent embedding 环境变量）、`deploy/*/​.env.example`、`backend/.env.example`、`.github/workflows/ci.yml`（CI Postgres 镜像）、`README.md`（重建容器说明、ingest 命令）、`docs/operations.md`（RDS vector 扩展权限）
  - 附带修复（非本切片范围、本地 Windows 验收阻断项）：`backend/serviceos_api/application/ui_visualizations.py` 的 Point 正则容忍 CRLF 检出（`core.autocrlf=true` 下该测试在本机 main 上已失败）；`backend/tests/test_database.py` round-trip 按 schema 过滤 metadata 并新增 knowledge schema 断言。
- 本地命令与结果（2026-10-16，Windows，一次性容器 `pgvector/pgvector:pg17` @127.0.0.1:55433）：
  - `uv run --project backend --locked pytest backend/tests --require-postgres` → **226 passed**（含 8 个新测试；1 个良性 SAWarning：alembic check 反射不识别 vector 类型，drift 检查仍通过）
  - `alembic upgrade head` → 0015 应用成功（extension + schema + 两表）
  - `python -m serviceos_api.knowledge_ingest` → 875 条（872 语料 + 3 手册），重跑幂等 exit=0；`--embed` 无凭据 exit=2（fail closed）
  - 真实检索冒烟：`"robot keeps losing the map"` + verified `t2352` → 命中 `qa-v1:robovac:r4`（E28 丢失地图）等 3 条；无 verified model → 0 条（PN 门控生效）
  - `export_openapi --check`、`contracts/proposed/v1/sync_implemented.py --check` → 通过（无 HTTP 契约漂移）
  - 三个 compose 配置 `docker compose config -q` → 通过
- 已知限制：~~真实 DashScope embedding 生成与多轮检索质量未测~~ **已于 2026-10-16 实测**：Provider=DashScope 原生多模态协议（`SERVICEOS_EMBEDDING_PROVIDER=dashscope_multimodal`，model `qwen3-vl-embedding`，base `https://dashscope.aliyuncs.com`，1024 维）；`knowledge_ingest --embed` 对 875 分段全量向量化成功；跨语言冒烟：中文"吸奶器加热功能耗电吗？"经 vector 路径命中 heating 手册与 pump Q&A（纯关键词时为 0 命中）；真实 Agent run 的 `knowledge_references` 同时含 keyword/vector/fused 三种路径。Adapter 支持双协议（openai_compatible / dashscope_multimodal），均有 MockTransport 测试。
- 其余限制：中文查询在**未配置** embedding 时仍诚实返回空（降级行为）；评测基准集（240 条客诉）仍是后续切片。
- 对 `docs/development-plan.md` 勾选的影响：无（本切片是后续增量，不改阶段验收状态）。

