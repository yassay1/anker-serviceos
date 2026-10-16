"""Explicit, idempotent ingestion of curated knowledge seeds into serviceos_knowledge.

Seeds are committed, source-labelled artifacts: the local manual files under
``knowledge/`` and the derived ``knowledge/corpus/qa-v1.jsonl``. Each seed file
becomes one document; its rows/files become segments. Ingestion never reads the
raw hackathon workbook, never invents content, and prunes seed documents whose
source hash no longer matches the committed seeds. ``--embed`` fills pgvector
embeddings through the explicitly configured provider; without credentials it
fails closed instead of writing partial or fabricated vectors.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from serviceos_api.integrations.embedding_adapter import EmbeddingAdapter, vector_literal
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.knowledge_models import (
    EMBEDDING_DIMENSIONS, KNOWLEDGE_SCHEMA, MANUAL_APPLICABILITY, KnowledgeDocument,
    KnowledgeDocumentVersion, KnowledgeEmbedding, KnowledgeSegment,
)
from serviceos_api.persistence.models import ServicePolicy
from serviceos_api.settings import Settings

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
CORPUS_FILE = KNOWLEDGE_DIR / "corpus" / "qa-v1.jsonl"
EMBED_BATCH_SIZE = 10


def _content_sha(title: str, content: str, models: list[str]) -> str:
    return hashlib.sha256("\n".join([title, content, ",".join(models)]).encode("utf-8")).hexdigest()


def _manual_documents() -> list[dict]:
    documents = []
    for filename, (applicability, models) in sorted(MANUAL_APPLICABILITY.items()):
        path = KNOWLEDGE_DIR / filename
        raw = path.read_bytes()
        text_content = raw.decode("utf-8")
        heading = next((line.lstrip("# ").strip() for line in text_content.splitlines()
                        if line.strip().startswith("# ")), filename)
        documents.append({
            "source_kind": "manual",
            "title": heading,
            "filename": filename,
            "media_type": "text/markdown",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "split_type": "ROW",
            "segments": [{
                "entry_key": f"manual:{filename}",
                "title": heading,
                "content": text_content,
                "models": [model.casefold() for model in models],
                "directories": [],
                "pdt": None,
                "source_status": "CURATED_LOCAL",
                "consumer_visible": "AGENT_INTERNAL",
                "applicability": applicability,
                "curation": {
                    "source_kind": "manual",
                    "source_ref": filename,
                    "derived_from": f"backend/serviceos_api/knowledge/{filename}",
                    "filter": "manually curated local manual",
                    "label": "",
                },
            }],
        })
    return documents


def _corpus_documents() -> list[dict]:
    raw = CORPUS_FILE.read_bytes()
    segments = []
    with CORPUS_FILE.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            models = [str(model).strip().casefold() for model in row.get("models", []) if str(model).strip()]
            applicability = ("MODELS:" + ",".join(sorted(model.upper() for model in models))
                             if models else "GENERIC_QA")
            curation = dict(row.get("curation", {}))
            curation.update({
                "source_kind": "qa_corpus",
                "source_ref": f"{row['source_workbook']}#{row['sheet']}!r{row['row']}",
            })
            segments.append({
                "entry_key": row["entry_key"],
                "title": row["title"],
                "content": row["content"],
                "models": models,
                "directories": row.get("directories", []),
                "pdt": row.get("pdt") or None,
                "source_status": row.get("status", ""),
                "consumer_visible": row.get("consumer_visible", ""),
                "applicability": applicability,
                "curation": curation,
            })
    return [{
        "source_kind": "seed_corpus",
        "title": "黑客松智能服务赛题 Q&A 语料 qa-v1（已 curation）",
        "filename": CORPUS_FILE.name,
        "media_type": "application/jsonl",
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "split_type": "ROW",
        "segments": segments,
    }]


def _structured_documents() -> list[dict]:
    documents = []
    for filename, applicability in (("orders-v1.jsonl", "REFERENCE_ORDER"),
                                    ("dealers-v1.jsonl", "REFERENCE_DEALER")):
        path = KNOWLEDGE_DIR / "corpus" / filename
        raw = path.read_bytes()
        segments = []
        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            curation = dict(row.get("curation", {}))
            curation.update({
                "source_kind": "structured_seed",
                "source_ref": f"{row['source_workbook']}#{row['sheet']}!r{row['row']}",
            })
            segments.append({
                "entry_key": row["entry_key"],
                "title": row["title"],
                "content": row["content"],
                "attrs": row.get("attrs", {}),
                "models": [],
                "directories": [],
                "pdt": None,
                "source_status": "CURATED_REFERENCE",
                "consumer_visible": "AGENT_INTERNAL",
                "applicability": applicability,
                "curation": curation,
            })
        documents.append({
            "source_kind": "seed_corpus",
            "title": f"黑客松赛题参考数据 {filename}（已 curation）",
            "filename": filename,
            "media_type": "application/jsonl",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "split_type": "ROW",
            "segments": segments,
        })
    return documents


def load_seed_documents() -> list[dict]:
    documents = _manual_documents() + _corpus_documents() + _structured_documents()
    keys = [segment["entry_key"] for document in documents for segment in document["segments"]]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate_entry_key_in_seeds")
    for document in documents:
        for segment in document["segments"]:
            segment["content_sha256"] = _content_sha(segment["title"], segment["content"], segment["models"])
    return documents


def ingest(session: Session, documents: list[dict] | None = None) -> dict:
    """Create/refresh seed documents and prune seeds removed from the committed set."""
    documents = load_seed_documents() if documents is None else documents
    expected_hashes = {document["content_hash"] for document in documents}
    pruned = 0
    for stale in session.scalars(select(KnowledgeDocument).where(
            KnowledgeDocument.source_kind.in_(("seed_corpus", "manual")),
            ~KnowledgeDocument.content_hash.in_(expected_hashes))).all():
        session.delete(stale)
        pruned += 1
    created_documents = refreshed_segments = 0
    for document_seed in documents:
        existing = session.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.content_hash == document_seed["content_hash"]))
        if existing is not None:
            if session.scalar(select(func.count()).select_from(KnowledgeSegment).where(
                    KnowledgeSegment.document_id == existing.id)):
                continue
            version = session.scalar(select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.document_id == existing.id,
                KnowledgeDocumentVersion.version == existing.current_version))
        else:
            existing = KnowledgeDocument(
                source_kind=document_seed["source_kind"], title=document_seed["title"],
                filename=document_seed["filename"], media_type=document_seed["media_type"],
                content_hash=document_seed["content_hash"], status="CHUNKED", current_version=1,
                split_type=document_seed["split_type"],
            )
            session.add(existing)
            session.flush()
            version = KnowledgeDocumentVersion(document_id=existing.id, version=1,
                                               content_hash=document_seed["content_hash"],
                                               status="CHUNKED")
            session.add(version)
            created_documents += 1
        session.flush()
        for index, segment_seed in enumerate(document_seed["segments"]):
            session.add(KnowledgeSegment(
                document_id=existing.id, version_id=version.id, chunk_index=index,
                skip_embedding=False, entry_key=segment_seed["entry_key"],
                title=segment_seed["title"], content=segment_seed["content"],
                content_sha256=segment_seed["content_sha256"], models=segment_seed["models"],
                directories=segment_seed["directories"], pdt=segment_seed["pdt"],
                source_status=segment_seed["source_status"],
                consumer_visible=segment_seed["consumer_visible"],
                applicability=segment_seed["applicability"], curation=segment_seed["curation"],
                attrs=segment_seed.get("attrs", {}),
            ))
            refreshed_segments += 1
    session.flush()
    _refresh_final_statuses(session)
    return {"documents": len(documents), "created_documents": created_documents,
            "segments": refreshed_segments, "pruned": pruned}


def _refresh_final_statuses(session: Session) -> None:
    rows = session.execute(select(
        KnowledgeDocument.id,
        func.count(KnowledgeSegment.id),
        func.count(KnowledgeEmbedding.segment_id),
    ).select_from(KnowledgeDocument).join(
        KnowledgeSegment, KnowledgeSegment.document_id == KnowledgeDocument.id,
    ).outerjoin(
        KnowledgeEmbedding, KnowledgeEmbedding.segment_id == KnowledgeSegment.id,
    ).where(KnowledgeSegment.skip_embedding.is_(False)).group_by(KnowledgeDocument.id)).all()
    for document_id, children, embedded in rows:
        document = session.get(KnowledgeDocument, document_id)
        if document is None or document.status == "FAILED":
            continue
        target = "EMBEDDED" if embedded >= children and children else "STORED"
        document.status = target
        for version in session.scalars(select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.document_id == document_id)).all():
            version.status = target


def embed_missing(session: Session, embedder: EmbeddingAdapter) -> int:
    """Embed segments without vectors, committing each batch so a failed rerun resumes."""
    if not embedder.configured:
        raise ValueError("embedding_provider_unconfigured")
    if embedder.settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError("embedding_dimensions_unsupported")
    rows = session.execute(select(KnowledgeSegment).outerjoin(
        KnowledgeEmbedding, KnowledgeEmbedding.segment_id == KnowledgeSegment.id,
    ).where(KnowledgeEmbedding.segment_id.is_(None),
            KnowledgeSegment.skip_embedding.is_(False))).scalars().all()
    table = KnowledgeEmbedding.__table__
    total = 0
    for start in range(0, len(rows), EMBED_BATCH_SIZE):
        batch = rows[start:start + EMBED_BATCH_SIZE]
        vectors = embedder.embed([f"{segment.title}\n{segment.content}" for segment in batch])
        for segment, vector in zip(batch, vectors):
            literal = vector_literal(vector)
            session.execute(pg_insert(table).values(
                segment_id=segment.id, model=embedder.settings.embedding_model,
                dimensions=EMBEDDING_DIMENSIONS, embedding=literal,
            ).on_conflict_do_update(
                index_elements=["segment_id"],
                set_={"model": embedder.settings.embedding_model, "dimensions": EMBEDDING_DIMENSIONS,
                      "embedding": literal, "embedded_at": func.now()},
            ))
        session.commit()
        total += len(batch)
    _refresh_final_statuses(session)
    session.flush()
    return total


def ingest_policies(session: Session) -> dict:
    """Upsert DMN-style policy rows; older versions of a rule become SUPERSEDED."""
    path = KNOWLEDGE_DIR / "corpus" / "policies-v1.jsonl"
    created = updated = 0
    seen: dict[str, int] = {}
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        seen[row["rule_id"]] = max(seen.get(row["rule_id"], 0), row["version"])
        existing = session.scalar(select(ServicePolicy).where(
            ServicePolicy.rule_id == row["rule_id"], ServicePolicy.version == row["version"]))
        if existing is not None:
            if existing.source_ref != row["source_ref"] or existing.remedies != row["remedies"]:
                existing.remedies = row["remedies"]
                existing.source_ref = row["source_ref"]
                updated += 1
            continue
        session.add(ServicePolicy(
            rule_id=row["rule_id"], version=row["version"], country=row["country"],
            channel=row["channel"], product_family=row["product_family"],
            warranty_state=row["warranty_state"], remedies=row["remedies"],
            status="ACTIVE", source_ref=row["source_ref"],
        ))
        created += 1
    for rule_id, top in seen.items():
        for stale in session.scalars(select(ServicePolicy).where(
                ServicePolicy.rule_id == rule_id, ServicePolicy.version < top,
                ServicePolicy.status == "ACTIVE")).all():
            stale.status = "SUPERSEDED"
            updated += 1
    session.flush()
    return {"policies_created": created, "policies_updated": updated}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest curated knowledge seeds.")
    parser.add_argument("--embed", action="store_true",
                        help="also generate embeddings via the configured provider")
    args = parser.parse_args(argv)
    settings = Settings.from_environment()
    if args.embed and not settings.embedding_configured:
        print("Refusing --embed: set SERVICEOS_EMBEDDING_MODEL, SERVICEOS_EMBEDDING_BASE_URL "
              "and SERVICEOS_EMBEDDING_API_KEY first.", file=sys.stderr)
        return 2
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        print(f"Only {EMBEDDING_DIMENSIONS}-dimensional embeddings are supported by migration 0017.",
              file=sys.stderr)
        return 2
    engine = build_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            summary = ingest(session)
            policies = ingest_policies(session)
            session.commit()
            embedded = embed_missing(session, EmbeddingAdapter(settings)) if args.embed else 0
            session.commit()
        print(f"knowledge schema: {KNOWLEDGE_SCHEMA}")
        print(f"seed documents: {summary['documents']} (created {summary['created_documents']}), "
              f"segments: {summary['segments']}, pruned documents: {summary['pruned']}, "
              f"policies: {policies['policies_created']} created / {policies['policies_updated']} updated, "
              f"embedded now: {embedded}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
