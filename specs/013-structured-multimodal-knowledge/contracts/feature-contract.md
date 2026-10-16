# 结构化数据双路召回与多模态知识入库 · 功能契约

状态：草案 v1（2026-10-16，用户确认：双路召回 / 图片现在支持 / sheet 自动路由+可覆盖）。
背景：赛题工作簿含订单信息（24 行）、经销商名录（336 行）与产品知识 Q&A；官方 SOP 要求
订单/质保作为 Agent 判保证据源、经销商规则（country 精准 + seller 模糊）决定寄修/补单 vs
引导联系商家；eufy S1 Pro 同名歧义须检索前消歧（已由 011 门控覆盖）。

## 1. 场景与责任

| 项目 | 内容 |
|---|---|
| 所属阶段、功能切片 | 后续增量 · specs/013-structured-multimodal-knowledge（扩展 012 管道与 011 检索） |
| 用户目标与入口 | 客服在 /desk 知识面板整本上传工作簿/表格/图片；Agent 经语义路（lookup_manual）与精确路（lookup_order/match_dealer）双路召回 |
| 涉及对象 | `KnowledgeSegment.attrs`（结构化 facet）、`KnowledgeSegment.image_key`（多模态原件引用）；新 Agent 工具两个；无新业务对象 |
| 负责人 | 同一人 |
| 契约状态 | 草案 v1，2026-10-16 |

## 2. 核心决策

1. **双路召回**：结构化数据一次上传同时产出 (a) 行文本化向量分段（语义路，复用 011 混合检索）与 (b) `attrs` facet（精确路，类型化工具查询）。精确操作（订单号→订单、质保期判定、经销商授权判定）**不依赖向量相似度**。
2. **表格不以图片形式入库**：原生 xlsx/csv 文本化（无损、双路可用）；图片嵌入仅用于截图/扫描件/图表（multimodal embedding，qwen3-vl-embedding）。openai_compatible provider 不支持图像内容时，图片分段仅以标题文本参与关键词路、不生成向量（文档终态 STORED），不伪造视觉语义。
3. **sheet 语义自动路由 + 可覆盖**：表头含"订单号"→ORDER；表头⊆{country,seller}→DEALER；含 Title+Content→QA；其余→ROW 通用；图片→IMAGE。上传表单可选 `sheet_overrides`（JSON：sheet 名→类型）覆盖。
4. 经销商匹配三态：`AUTHORIZED`（精准或唯一模糊候选）/`AMBIGUOUS`（多候选，列候选并转人工）/`UNAUTHORIZED`；模糊=归一化（casefold+去非字母数字）后包含或相似度≥0.8。
5. 质保判定为服务端确定性计算：返回 `warranty_end` + `in_warranty`（与服务器当前日期比较），不由模型推断。

## 3. HTTP / 工具操作

- 上传复用 `POST /api/v1/knowledge/documents`：新增可选 form 字段 `sheet_overrides`（JSON 字符串）；新增接受 jpeg/png/webp（≤10MB）。
- Agent 工具（内部，经租约围栏，只读）：
  - `lookup_order(order_no)`：attrs.order_no 精确匹配（大小写不敏感）；命中返回 SKU/描述/购买日/质保到期/in_warranty/状态/承运商/单号/金额 + SOURCE 引用；未命中明示"参考数据中无该订单号"，不得推断。
  - `match_dealer(country, seller)`：三态结果 + 命中/候选 seller 原值 + SOURCE 引用。
- 无新增公开 HTTP 路由；OpenAPI 仅上传字段扩展。

## 4. 数据与迁移

- 0015（未上线，就地修订）：`knowledge_segments` 增 `attrs JSONB NOT NULL DEFAULT '{}'`、`image_key TEXT`；`split_type` 检查增 `IMAGE`。
- 本地已应用旧 0015 的库：`alembic downgrade 0014 && upgrade head` 后重跑 ingestion。
- facet 键稳定小写蛇形：order/sku/description/qty/purchase_date/warranty_end/address/status/carrier/tracking/logistics_status/ship_date/amount；dealer：country/seller/seller_norm。

## 5. 验收

| 路径 | 预期 | 证据 |
|---|---|---|
| 工作簿整本上传 | 各 sheet 按语义路由；订单行带 attrs.order_no/warranty_end；经销商行带 country/seller_norm；Q&A 行无 attrs | test_knowledge_structured.py |
| 语义路 | "发往澳大利亚的订单用哪家承运商" 类查询可召回订单分段 | 同上 |
| lookup_order | 精确命中+in_warranty 正确（含 2026-10-13 边界行）；未命中诚实空结果 | 同上 |
| match_dealer | 精准/唯一模糊/多候选/无候选 四路径三态正确 | 同上 |
| 图片入库 | png 上传→IMAGE 分段；dashscope fake adapter 收到 {"image": base64} 内容；openai provider 下图片无向量且文档 STORED | 同上 |
| sheet_overrides | 覆盖生效（把 QA sheet 强制 ROW 等） | 同上 |
| 回归 | 011/012 全部测试 + 全量套件绿 | 命令记录 |

## 6. 明确不包含

Text2SQL/任意查询、客户上传进全局知识库、图片 OCR 文本化、经销商/订单数据租户隔离（赛题参考数据为全局）、S1 Pro 歧义的额外提示强化（011 门控已覆盖）。

## 7. 变更与落地记录

- 决策确认：2026-10-16（双路/图片现在/自动+覆盖）。
- 实现后回填。
