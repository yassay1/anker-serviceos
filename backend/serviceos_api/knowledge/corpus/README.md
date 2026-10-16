# Curated Q&A corpus `qa-v1`

Derived, reviewable seed for the `serviceos_knowledge` retrieval store. Not a raw copy of the
hackathon workbook: rows are filtered, normalized to single-line text, and every entry carries
provenance metadata.

- Source: `data/reference/hackathon/黑客松智能服务赛题资料.xlsx`
  (sha256 `0279f939182e84526c05dfc5e1b5a694248ab5acfe4bec7ea4857f9504051f94`, refreshed at origin commit `0438551`;
  the Q&A sheets are content-identical to the previous export `0cc02e65…`, verified by row-level diff on 2026-10-16)
- Filter: `Status=Published AND Consumer Visible=Visible`
- Entries: 872 (`eufy Robovacs Q&A` 593, `eufy Breast Pump Q&A` 279; 3 Invisible rows excluded)
- Seed file sha256: `c382622c6a21d1743bbd3eacdb2eb53883ed846d8170c922c17b32b58680672c`
- Status label on every entry: 赛题参考数据（已脱敏），非已核验厂商政策；引用时保留来源与适用型号。

`models` holds the workbook PN codes (e.g. `T2352;T2353` split into a list). Retrieval only
returns model-restricted entries when the linked device model is VERIFIED, mirroring the
existing manual gating.

Regeneration (one-off, outside the locked backend environment):

```powershell
uv run --with openpyxl python <script> # see specs/011 contract for the expected counts/hashes
```

Ingestion into the database:

```powershell
uv run --project backend --locked python -m serviceos_api.knowledge_ingest          # keyword-only
uv run --project backend --locked python -m serviceos_api.knowledge_ingest --embed  # + vectors
```
