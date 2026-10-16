"""Hybrid keyword + vector retrieval over the curated knowledge store.

Read-only for Agent tools. The keyword path always works; the vector path is
active only when an embedding provider is explicitly configured and vectors
exist. Any embedding failure degrades that call to keyword-only results and is
never surfaced as fabricated relevance. Query text is not logged. Child hits
carry their parent's title path and first paragraph for context expansion.
"""

import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from serviceos_api.integrations.embedding_adapter import EmbeddingAdapter, EmbeddingUnavailable, vector_literal
from serviceos_api.persistence.knowledge_models import KnowledgeEmbedding, KnowledgeSegment
from serviceos_api.settings import Settings

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
EXCERPT_CHAR_LIMIT = 1600

# Curated same-name product families: a query mentioning one of these names without a
# VERIFIED device model must trigger requirement clarification, not a guessed family.
AMBIGUOUS_PRODUCTS = {
    "s1 pro": (
        ("扫地机器人 S1 Pro Omni", "t2080"),
        ("穿戴式吸奶器 S1 Pro", "t8d04"),
    ),
}


_PRODUCT_DENIAL = re.compile(r"(?:没(?:有)?(?:说|提到|提及|问|提过)|未(?:说|提到|提及)|不(?:是|问|提到)|不是(?:在问)?)\s*$")


def _customer_named_alias(text: str, alias: str) -> bool:
    folded = text.casefold()
    for match in re.finditer(re.escape(alias), folded):
        prefix = folded[max(0, match.start() - 14):match.start()]
        if not _PRODUCT_DENIAL.search(prefix):
            return True
    return False


def detect_ambiguity(query: str, verified_models: set[str]) -> list[tuple[str, str]]:
    """Return conflicting (label, model) candidates visible to the agent, else []."""
    verified = {model.casefold() for model in verified_models}
    for name, candidates in AMBIGUOUS_PRODUCTS.items():
        if _customer_named_alias(query, name):
            unresolved = [candidate for candidate in candidates if candidate[1] not in verified]
            if len(unresolved) >= 2:
                return list(unresolved)
    return []


def ground_retrieval_query(query: str, customer_text: str,
                           verified_models: set[str]) -> tuple[str, tuple[str, ...]]:
    """Prevent a model-authored query from introducing a known ambiguous product alias.

    Model-generated issue wording remains useful for retrieval, but a product alias is
    grounded only when the customer said it or a matching candidate model is verified.
    """
    query_folded = query.casefold()
    verified = {model.casefold() for model in verified_models}
    ungrounded = tuple(
        alias for alias, candidates in AMBIGUOUS_PRODUCTS.items()
        if alias in query_folded and not _customer_named_alias(customer_text, alias)
        and not any(model in verified for _, model in candidates)
    )
    return (customer_text.strip(), ungrounded) if ungrounded and customer_text.strip() else (query, ())


def search_tokens(value: str) -> set[str]:
    normalized = value.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", normalized)
    for run in cjk_runs:
        tokens.update(run[index:index + 2] for index in range(len(run) - 1))
        if len(run) == 1:
            tokens.add(run)
    return tokens


@dataclass(frozen=True)
class RetrievedKnowledge:
    entry_key: str
    source_kind: str
    source_ref: str
    source_sha256: str
    applicability: str
    excerpt: str
    curation_label: str = ""
    path: str = "fused"

    def content_item(self) -> str:
        note = f" | NOTE: {self.curation_label}" if self.curation_label else ""
        return (f"SOURCE: {self.source_ref} | VERSION: sha256:{self.source_sha256[:16]} | "
                f"APPLICABILITY: {self.applicability}{note}\n{self.excerpt}")


@dataclass(frozen=True)
class RetrievalResult:
    items: list[RetrievedKnowledge]
    references: list[dict]
    stages: list[str]


@dataclass
class KnowledgeRetrieval:
    session: Session
    settings: Settings | None = None
    embedder: EmbeddingAdapter | None = None
    keyword_candidates: int = 20
    vector_candidates: int = 20
    rrf_k: int = 60
    top_results: int = 3
    _embedder_resolved: bool = field(default=False, init=False, repr=False)

    def _resolved_embedder(self) -> EmbeddingAdapter | None:
        if not self._embedder_resolved:
            self._embedder_resolved = True
            if self.embedder is None and self.settings is not None and self.settings.embedding_configured:
                self.embedder = EmbeddingAdapter(self.settings)
        return self.embedder

    def corpus_available(self) -> bool:
        return bool(self.session.scalar(select(func.count()).select_from(KnowledgeSegment)))

    def search(self, query: str, verified_models: set[str], *, gate: bool = True,
               top: int | None = None) -> RetrievalResult:
        limit = top or self.top_results
        light = self.session.execute(select(KnowledgeSegment.id, KnowledgeSegment.models).where(
            KnowledgeSegment.skip_embedding.is_(False))).all()
        verified = {model.casefold() for model in verified_models}
        gated_ids = [row.id for row in light
                     if not gate or not row.models or (set(row.models) & verified)]
        if not gated_ids:
            return RetrievalResult(items=[], references=[], stages=[])
        keyword_ids = self._keyword_ids(query, gated_ids)
        vector_ids, vector_ok = self._vector_ids(query, gated_ids)
        rows = self._load(set(keyword_ids) | set(vector_ids))
        by_id = {row.id: row for row in rows}
        keyword_rank = [by_id[segment_id] for segment_id in
                        self._score_order(query, [by_id[i] for i in keyword_ids if i in by_id])]
        vector_rank = [by_id[segment_id] for segment_id in vector_ids if segment_id in by_id]
        stages = ["keyword"] + (["vector"] if vector_ok else [])
        fused: dict[UUID, float] = {}
        for ranking in (keyword_rank, vector_rank):
            for rank, segment in enumerate(ranking):
                fused[segment.id] = fused.get(segment.id, 0.0) + 1.0 / (self.rrf_k + rank + 1)
        keyword_ids_set = {segment.id for segment in keyword_rank}
        vector_ids_set = {segment.id for segment in vector_rank}
        ordered = sorted(fused, key=lambda segment_id: (-fused[segment_id], by_id[segment_id].entry_key))
        stages.append("fused")
        tokens = search_tokens(query)
        parents = self._parents([by_id[segment_id] for segment_id in ordered[:limit]])
        items, references = [], []
        for segment_id in ordered[:limit]:
            segment = by_id[segment_id]
            path = ("fused" if segment_id in keyword_ids_set and segment_id in vector_ids_set
                    else "vector" if segment_id in vector_ids_set else "keyword")
            items.append(self._present(segment, tokens, parents.get(segment.parent_segment_id), path))
            references.append({
                "entry_key": segment.entry_key,
                "source_ref": str((segment.curation or {}).get("source_ref", segment.title)),
                "source_sha256_16": segment.content_sha256[:16],
                "path": path,
            })
        return RetrievalResult(items=items, references=references, stages=stages)

    def _vector_active(self) -> bool:
        embedder = self._resolved_embedder()
        return embedder is not None and embedder.configured

    def _load(self, ids) -> list[KnowledgeSegment]:
        if not ids:
            return []
        return list(self.session.scalars(select(KnowledgeSegment).where(
            KnowledgeSegment.id.in_(ids))).all())

    def _keyword_ids(self, query: str, gated_ids: list[UUID]) -> list[UUID]:
        """SQL prefilter (tsvector + trgm/CJK LIKE); Python re-scores the subset."""
        tokens = search_tokens(query)
        latin = [token for token in sorted(tokens) if token.isascii() and len(token) >= 3]
        short = [token for token in sorted(tokens) if token.isascii() and len(token) < 3][:4]
        runs = re.findall(r"[\u3400-\u9fff]+", query.casefold())[:6]
        conditions, params = [], {"ids": [str(value) for value in gated_ids]}
        if latin:
            conditions.append("search_vector @@ to_tsquery('simple', :latin)")
            params["latin"] = " | ".join(latin)
        for index, token in enumerate(short):
            conditions.append(f"content ILIKE :short{index}")
            params[f"short{index}"] = f"%{token}%"
        for index, run in enumerate(runs):
            conditions.append(f"content LIKE :cjk{index}")
            params[f"cjk{index}"] = f"%{run}%"
        if not conditions:
            return []
        sql = text(
            f"SELECT id FROM {KnowledgeSegment.__table__.fullname} "
            "WHERE id = ANY(CAST(:ids AS uuid[])) AND (" + " OR ".join(conditions) + ")")
        return [row[0] for row in self.session.execute(sql, params).all()]

    def _score_order(self, query: str, rows: list[KnowledgeSegment]) -> list[UUID]:
        tokens = search_tokens(query)
        if not tokens:
            return []
        scored = []
        for segment in rows:
            title_score = 2 * len(tokens & search_tokens(segment.title))
            body_score = len(tokens & search_tokens(segment.content))
            score = title_score + body_score
            if score:
                scored.append((score, segment))
        scored.sort(key=lambda item: (-item[0], item[1].entry_key))
        return [segment.id for _, segment in scored[:self.keyword_candidates]]

    def _vector_ids(self, query: str, gated_ids: list[UUID]) -> tuple[list[UUID], bool]:
        if not self._vector_active():
            return [], False
        try:
            query_vector = self.embedder.embed([query])[0]
        except (EmbeddingUnavailable, RuntimeError):
            # Degrade this call to keyword-only; never fabricate vector relevance.
            return [], False
        rows = self.session.execute(text(
            f"SELECT segment_id FROM {KnowledgeEmbedding.__table__.fullname} "
            "WHERE segment_id = ANY(CAST(:ids AS uuid[])) "
            "ORDER BY embedding <=> CAST(:query_vector AS vector) LIMIT :limit"
        ), {"ids": [str(value) for value in gated_ids], "query_vector": vector_literal(query_vector),
            "limit": self.vector_candidates}).all()
        return [row[0] for row in rows], True

    def _parents(self, segments: list[KnowledgeSegment]) -> dict[UUID, KnowledgeSegment]:
        parent_ids = {segment.parent_segment_id for segment in segments if segment.parent_segment_id}
        if not parent_ids:
            return {}
        rows = self.session.scalars(select(KnowledgeSegment).where(
            KnowledgeSegment.id.in_(parent_ids))).all()
        return {row.id: row for row in rows}

    def _present(self, segment: KnowledgeSegment, tokens: set[str],
                 parent: KnowledgeSegment | None, path: str) -> RetrievedKnowledge:
        paragraphs = [" ".join(part.split()) for part in _PARAGRAPH_SPLIT.split(segment.content) if part.strip()]
        scored = sorted(((len(tokens & search_tokens(paragraph)), paragraph) for paragraph in paragraphs),
                        key=lambda item: item[0], reverse=True)
        matched = [paragraph for score, paragraph in scored if score][:4]
        body = "\n".join(matched) if matched else " ".join(segment.content.split())
        title = segment.title
        if parent is not None:
            parent_paragraphs = [" ".join(part.split())
                                 for part in _PARAGRAPH_SPLIT.split(parent.content) if part.strip()]
            first = parent_paragraphs[0] if parent_paragraphs else ""
            title = f"{parent.title} > {segment.title}"
            if first and first not in body:
                body = f"{first}\n{body}"
        excerpt = f"{title}\n{body}"[:EXCERPT_CHAR_LIMIT]
        label = str((segment.curation or {}).get("label", ""))
        return RetrievedKnowledge(
            entry_key=segment.entry_key,
            source_kind=self._source_kind(segment),
            source_ref=str((segment.curation or {}).get("source_ref", segment.title)),
            source_sha256=segment.content_sha256,
            applicability=segment.applicability,
            excerpt=excerpt,
            curation_label=label,
            path=path,
        )

    @staticmethod
    def _source_kind(segment: KnowledgeSegment) -> str:
        return str((segment.curation or {}).get("source_kind", ""))
