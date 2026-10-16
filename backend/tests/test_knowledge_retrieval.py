"""Hybrid knowledge retrieval: idempotent ingestion, model gating, RRF fusion, degradation."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from serviceos_api.application.agent_services import AgentToolService
from serviceos_api.application.knowledge_retrieval import KnowledgeRetrieval
from serviceos_api.integrations.embedding_adapter import (
    EmbeddingAdapter, EmbeddingUnavailable, vector_literal,
)
from serviceos_api.knowledge_ingest import _content_sha, embed_missing, ingest, load_seed_documents
from serviceos_api.persistence.knowledge_models import (
    KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeEmbedding, KnowledgeSegment,
)
from serviceos_api.persistence.models import AgentRun
from serviceos_api.settings import Settings
from test_worker_runtime import seed_message

UNIT_VECTOR = [1.0] + [0.0] * 1023


def _doc_pair(session, source_kind="seed_corpus", content_hash=None):
    document = KnowledgeDocument(
        source_kind=source_kind, title="test doc", filename="t.xlsx", media_type="application/jsonl",
        content_hash=content_hash or uuid4().hex, status="CHUNKED", current_version=1, split_type="ROW",
    )
    session.add(document)
    session.flush()
    version = KnowledgeDocumentVersion(document_id=document.id, version=1,
                                       content_hash=document.content_hash, status="CHUNKED")
    session.add(version)
    session.flush()
    return document, version


def _segment(session, document, version, entry_key, title, content, models=(),
             applicability="GENERIC_QA", source_kind="qa_corpus", label="测试语料，非已核验政策",
             skip=False, parent=None, index=0):
    segment = KnowledgeSegment(
        document_id=document.id, version_id=version.id, chunk_index=index,
        parent_segment_id=parent, skip_embedding=skip, entry_key=entry_key,
        title=title, content=content,
        content_sha256=_content_sha(title, content, [model.casefold() for model in models]),
        models=[model.casefold() for model in models], directories=[], pdt=None,
        source_status="Published", consumer_visible="Visible", applicability=applicability,
        curation={"source_kind": source_kind, "source_ref": f"test-workbook.xlsx#Sheet!{entry_key}",
                  "label": label},
    )
    session.add(segment)
    session.flush()
    return segment


def _seed_doc(entry_key, content, hash_seed):
    return {
        "source_kind": "manual", "title": "t", "filename": "t.md", "media_type": "text/markdown",
        "content_hash": hashlib.sha256(hash_seed.encode()).hexdigest(), "split_type": "ROW",
        "segments": [{
            "entry_key": entry_key, "title": "t", "content": content, "models": [], "directories": [],
            "pdt": None, "source_status": "CURATED_LOCAL", "consumer_visible": "AGENT_INTERNAL",
            "applicability": "generic",
            "curation": {"source_kind": "manual", "source_ref": "t.md", "label": ""},
            "content_sha256": _content_sha("t", content, []),
        }],
    }


class FakeEmbedder(EmbeddingAdapter):
    """Deterministic stand-in; never touches the network."""

    def __init__(self, error=None):
        settings = Settings(environment="test", embedding_model="fake-embed",
                            embedding_api_key="test-key",
                            embedding_base_url="https://embed.invalid/v1")
        super().__init__(settings)
        self._error = error
        self.calls = 0
        self.last_contents = None

    def embed_contents(self, contents):
        self.calls += 1
        self.last_contents = contents
        if self._error is not None:
            raise self._error
        return [list(UNIT_VECTOR) for _ in contents]


def active_run(session):
    tenant, _, conversation, message, job, _ = seed_message(session)
    token = uuid4()
    job.status = "RUNNING"
    job.attempt_count = 1
    job.lease_token = token
    job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                   message_id=message.id, thread_id=str(conversation.id), lease_token=token,
                   provider="test", model="test")
    session.add(run)
    session.flush()
    return tenant, conversation, run


def _purge(session):
    for document in session.scalars(select(KnowledgeDocument)).all():
        session.delete(document)
    session.flush()


def test_committed_seeds_ingest_idempotently(db_session):
    _purge(db_session)
    documents = load_seed_documents()
    manuals = [doc for doc in documents if doc["source_kind"] == "manual"]
    corpus = [doc for doc in documents if doc["source_kind"] == "seed_corpus"]
    assert len(manuals) == 3 and len(corpus) == 3
    assert sum(len(doc["segments"]) for doc in corpus) == 872 + 24 + 336
    first = ingest(db_session, documents)
    assert first["documents"] == 6 and first["created_documents"] == 6 and first["segments"] == 1235
    assert db_session.scalar(select(func.count()).select_from(KnowledgeSegment)) == 1235
    second = ingest(db_session, documents)
    assert second["created_documents"] == 0 and second["segments"] == 0 and second["pruned"] == 0
    assert db_session.scalar(select(func.count()).select_from(KnowledgeSegment)) == 1235


def test_ingest_prunes_stale_seed_documents_and_cascades_embeddings(db_session):
    ingest(db_session, [_seed_doc("manual:t", "alpha body text", "v1")])
    segment = db_session.scalar(select(KnowledgeSegment).where(KnowledgeSegment.entry_key == "manual:t"))
    db_session.add(KnowledgeEmbedding(segment_id=segment.id, model="fake", dimensions=1024,
                                      embedding=vector_literal(UNIT_VECTOR)))
    db_session.flush()
    summary = ingest(db_session, [_seed_doc("manual:t2", "beta body text", "v2")])
    assert summary["pruned"] == 1
    assert db_session.scalar(select(func.count()).select_from(KnowledgeEmbedding)) == 0
    assert [row.entry_key for row in db_session.scalars(select(KnowledgeSegment)).all()] == ["manual:t2"]


def test_keyword_search_gates_by_verified_model_and_keeps_output_contract(db_session):
    _purge(db_session)
    document, version = _doc_pair(db_session)
    _segment(db_session, document, version, "qa-v1:t:r1", "robot loses map",
             "The robot keeps losing the map after cleaning.", models=["t2352"],
             applicability="MODELS:T2352")
    _segment(db_session, document, version, "manual:generic.md", "charging basics",
             "Check the charging cable and port.", source_kind="manual",
             applicability="generic_no_charge", label="", index=1)
    retrieval = KnowledgeRetrieval(db_session)
    assert retrieval.corpus_available()
    assert retrieval.search("losing map", set()).items == []
    result = retrieval.search("losing map", {"T2352"})
    assert [item.entry_key for item in result.items] == ["qa-v1:t:r1"]
    content = result.items[0].content_item()
    assert content.startswith("SOURCE: test-workbook.xlsx#Sheet!qa-v1:t:r1 | VERSION: sha256:")
    assert "APPLICABILITY: MODELS:T2352" in content
    assert "NOTE: 测试语料，非已核验政策" in content
    assert "robot loses map" in content
    assert result.references[0]["path"] == "keyword"
    assert result.stages == ["keyword", "fused"]


def test_vector_path_adds_entries_without_keyword_overlap(db_session):
    _purge(db_session)
    document, version = _doc_pair(db_session)
    target = _segment(db_session, document, version, "qa-v1:t:r1", "zzz unrelated entry",
                      "qqq content about wiring harness")
    _segment(db_session, document, version, "qa-v1:t:r2", "robot loses map",
             "The robot keeps losing the map", index=1)
    db_session.add(KnowledgeEmbedding(segment_id=target.id, model="fake", dimensions=1024,
                                      embedding=vector_literal(UNIT_VECTOR)))
    db_session.flush()
    embedder = FakeEmbedder()
    result = KnowledgeRetrieval(db_session, embedder=embedder).search("robot losing map", set())
    keys = [item.entry_key for item in result.items]
    assert "qa-v1:t:r2" in keys and "qa-v1:t:r1" in keys
    assert embedder.calls == 1
    paths = {item.entry_key: item.path for item in result.items}
    assert paths["qa-v1:t:r1"] == "vector" and paths["qa-v1:t:r2"] == "keyword"
    assert result.stages == ["keyword", "vector", "fused"]


def test_embedding_failure_degrades_to_keyword_only(db_session):
    _purge(db_session)
    document, version = _doc_pair(db_session)
    _segment(db_session, document, version, "qa-v1:t:r2", "robot loses map",
             "The robot keeps losing the map")
    retrieval = KnowledgeRetrieval(db_session, embedder=FakeEmbedder(error=EmbeddingUnavailable("boom")))
    result = retrieval.search("robot losing map", set())
    assert [item.entry_key for item in result.items] == ["qa-v1:t:r2"]
    assert result.stages == ["keyword", "fused"]


def test_parent_segment_expands_child_excerpt(db_session):
    _purge(db_session)
    document, version = _doc_pair(db_session, source_kind="manual")
    parent = _segment(db_session, document, version, "manual:p", "加热安全总则",
                      "加热功能仅适用于干燥环境。\n\n其余总则内容。", skip=True,
                      source_kind="manual", label="", applicability="generic")
    child = _segment(db_session, document, version, "manual:p:c1", "加热耗电",
                     "加热十分钟额外耗电约两成。", parent=parent.id, index=1,
                     source_kind="manual", label="", applicability="generic")
    result = KnowledgeRetrieval(db_session).search("加热 耗电", set())
    assert [item.entry_key for item in result.items] == [child.entry_key]
    excerpt = result.items[0].excerpt
    assert excerpt.startswith("加热安全总则 > 加热耗电")
    assert "加热功能仅适用于干燥环境。" in excerpt


def test_embed_missing_requires_provider_and_resumes(db_session):
    _purge(db_session)
    document, version = _doc_pair(db_session)
    for index in range(3):
        _segment(db_session, document, version, f"qa-v1:t:r{index}", f"guide {index}",
                 f"body {index}", index=index)
    with pytest.raises(ValueError, match="embedding_provider_unconfigured"):
        embed_missing(db_session, EmbeddingAdapter(Settings(environment="test")))
    embedder = FakeEmbedder()
    assert embed_missing(db_session, embedder) == 3
    assert db_session.scalar(select(func.count()).select_from(KnowledgeEmbedding)) == 3
    assert embed_missing(db_session, embedder) == 0


def test_settings_reject_unsupported_embedding_dimensions():
    with pytest.raises(ValueError, match="1024"):
        Settings(environment="test", embedding_dimensions=768)


def test_embedding_adapter_parses_openai_compatible_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.content)
        assert body["dimensions"] == 1024 and body["input"] == ["a", "b"]
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.0] * 1024},
            {"index": 0, "embedding": [1.0] * 1024},
        ]})

    settings = Settings(environment="test", embedding_model="m", embedding_api_key="test-key",
                        embedding_base_url="https://embed.invalid/v1")
    adapter = EmbeddingAdapter(settings, transport=httpx.MockTransport(handler))
    vectors = adapter.embed(["a", "b"])
    assert vectors[0][0] == 1.0 and vectors[1][0] == 0.0 and len(vectors) == 2


def test_embedding_adapter_rejects_dimension_mismatch_and_bad_shapes():
    settings = Settings(environment="test", embedding_model="m", embedding_api_key="test-key",
                        embedding_base_url="https://embed.invalid/v1")
    short = httpx.MockTransport(lambda request: httpx.Response(
        200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}))
    with pytest.raises(EmbeddingUnavailable, match="dimension"):
        EmbeddingAdapter(settings, transport=short).embed(["a"])
    mismatch = httpx.MockTransport(lambda request: httpx.Response(
        200, json={"data": [{"index": 0, "embedding": [1.0] * 1024}]}))
    with pytest.raises(EmbeddingUnavailable, match="mismatch"):
        EmbeddingAdapter(settings, transport=mismatch).embed(["a", "b"])


def test_embedding_adapter_dashscope_multimodal_protocol():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        body = json.loads(request.content)
        seen["body"] = body
        return httpx.Response(200, json={"output": {"embeddings": [
            {"index": 0, "embedding": [0.5] * 1024, "type": "text"},
        ]}})

    settings = Settings(environment="test", embedding_model="qwen3-vl-embedding",
                        embedding_api_key="test-key", embedding_base_url="https://dashscope.invalid",
                        embedding_provider="dashscope_multimodal")
    vectors = EmbeddingAdapter(settings, transport=httpx.MockTransport(handler)).embed(["加热耗电"])
    assert vectors == [[0.5] * 1024]
    assert seen["path"] == "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
    assert seen["body"]["input"]["contents"] == [{"text": "加热耗电"}]
    assert seen["body"]["parameters"]["dimension"] == 1024


def test_settings_reject_unknown_embedding_provider():
    with pytest.raises(ValueError, match="provider"):
        Settings(environment="test", embedding_provider="nope")


def test_lookup_manual_envelope_corpus_and_audit(db_session):
    tenant, conversation, run = active_run(db_session)
    service = AgentToolService(db_session, tenant.id, conversation.id, run.id, run.lease_token,
                                 settings=Settings(environment="test"))
    envelope = service.lookup_manual("losing map after cleaning", verified_models={"t2352"})
    assert envelope.status == "OK"
    text = envelope.to_prompt_text(5000)
    assert "SOURCE:" in text and len(text) <= 5000
    assert envelope.references and envelope.references[0]["entry_key"].startswith("qa-v1:robovac:")
    db_session.refresh(run)
    assert run.result_payload["knowledge_references"] == envelope.references
    assert run.result_payload["retrieval_path"] == "corpus"
    assert run.result_payload["tool_envelopes"][-1]["tool"] == "lookup_manual"


def test_lookup_manual_without_corpus_is_typed_not_found(db_session):
    for document in db_session.scalars(select(KnowledgeDocument)).all():
        db_session.delete(document)
    db_session.flush()
    tenant, conversation, run = active_run(db_session)
    service = AgentToolService(db_session, tenant.id, conversation.id, run.id, run.lease_token,
                                 settings=Settings(environment="test"))
    envelope = service.lookup_manual("不充电", verified_models=set())
    assert envelope.status == "NOT_FOUND" and envelope.items == []
    assert "语料未导入" in envelope.to_prompt_text()
    db_session.refresh(run)
    assert run.result_payload["retrieval_path"] == "none"


def test_detect_ambiguity_requires_two_unresolved_candidates():
    from serviceos_api.application.knowledge_retrieval import detect_ambiguity
    assert len(detect_ambiguity("我的 S1 Pro 吸力小", set())) == 2
    assert detect_ambiguity("我的 S1 Pro 吸力小", {"t8d04"}) == []
    assert detect_ambiguity("我的 E28 丢地图", set()) == []


def test_lookup_manual_returns_disambiguation_conflict_without_verified_model(db_session):
    tenant, conversation, run = active_run(db_session)
    service = AgentToolService(db_session, tenant.id, conversation.id, run.id, run.lease_token,
                               settings=Settings(environment="test"))
    envelope = service.lookup_manual("S1 Pro 吸力变小是不是电池不行", verified_models=set())
    assert envelope.applicability == "DISAMBIGUATION_REQUIRED"
    assert len(envelope.items) == 2
    joined = "".join(envelope.items)
    assert "扫地机器人" in joined and "吸奶器" in joined
    assert "需求澄清" in envelope.notes[0]
    db_session.refresh(run)
    assert run.result_payload["disambiguation_required"] is True
    resolved = service.lookup_manual("S1 Pro 加热耗电", verified_models={"t8d04"})
    assert resolved.applicability != "DISAMBIGUATION_REQUIRED"
