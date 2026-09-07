"""论文雷达 embedding provider 测试。"""

import numpy as np
import pytest
import sys
import types
from types import SimpleNamespace

from paper_graph.radar_embeddings import get_embedding_provider, lexical_embeddings, sentence_transformer_embeddings


def test_lexical_embeddings_are_stable_and_non_zero():
    first = lexical_embeddings(["multimodal retrieval", "graph learning"])
    second = lexical_embeddings(["multimodal retrieval", "graph learning"])
    assert first == second
    assert len(first[0]) == 512
    assert np.linalg.norm(first[0]) > 0


def test_get_embedding_provider_defaults_to_sentence_transformer(monkeypatch):
    monkeypatch.delenv("RADAR_EMBEDDING_PROVIDER", raising=False)
    assert get_embedding_provider() is sentence_transformer_embeddings


def test_get_embedding_provider_supports_lexical(monkeypatch):
    monkeypatch.setenv("RADAR_EMBEDDING_PROVIDER", "lexical")
    assert get_embedding_provider() is lexical_embeddings


def test_sentence_transformer_uses_daily_arxiv_encode_params(monkeypatch):
    calls = {}

    class FakeEncoder:
        def __init__(self, model, trust_remote_code):
            calls["init"] = (model, trust_remote_code)

        def encode(self, texts, **kwargs):
            calls["encode"] = (texts, kwargs)
            return np.asarray([[0.1, 0.2] for _ in texts])

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeEncoder))
    monkeypatch.setenv("RADAR_EMBEDDING_MODEL", "daily/model")
    monkeypatch.setenv("RADAR_EMBEDDING_TASK", "retrieval")
    monkeypatch.setenv("RADAR_EMBEDDING_PROMPT_NAME", "document")
    monkeypatch.setenv("RADAR_EMBEDDING_TRUST_REMOTE_CODE", "true")
    import paper_graph.radar_embeddings as embeddings

    embeddings._LOCAL_ENCODER = None
    embeddings._LOCAL_ENCODER_KEY = None
    assert embeddings.sentence_transformer_embeddings(["paper"]) == [[0.1, 0.2]]
    assert calls["init"] == ("daily/model", True)
    assert calls["encode"] == (["paper"], {"task": "retrieval", "prompt_name": "document", "show_progress_bar": False})


def test_get_embedding_provider_rejects_unknown(monkeypatch):
    monkeypatch.setenv("RADAR_EMBEDDING_PROVIDER", "unknown")
    with pytest.raises(RuntimeError, match="不支持的 RADAR_EMBEDDING_PROVIDER"):
        get_embedding_provider()


def test_api_embeddings_batches_requests(monkeypatch):
    import paper_graph.radar_embeddings as embeddings

    calls = []

    class FakeEmbeddings:
        def create(self, *, input, model):
            calls.append((input, model))
            return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(text))]) for text in input])

    monkeypatch.setattr(embeddings, "OpenAI", lambda **kwargs: SimpleNamespace(embeddings=FakeEmbeddings()))
    monkeypatch.setenv("RADAR_EMBEDDING_API_KEY", "key")
    monkeypatch.setenv("RADAR_EMBEDDING_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("RADAR_EMBEDDING_MODEL", "embed")
    monkeypatch.setenv("RADAR_EMBEDDING_BATCH_SIZE", "2")
    assert embeddings.api_embeddings(["a", "bb", "ccc"]) == [[1.0], [2.0], [3.0]]
    assert calls == [(["a", "bb"], "embed"), (["ccc"], "embed")]
