"""论文雷达 embedding provider。

默认复用 daily arxiv 的本地 SentenceTransformer 模型，API 与 lexical 保留为可选路径。
"""

from __future__ import annotations

import hashlib
import os
import re

import numpy as np
from openai import OpenAI


TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]")
_LOCAL_ENCODER = None
_LOCAL_ENCODER_KEY: tuple[str, bool] | None = None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def lexical_embeddings(texts: list[str], dimensions: int = 512) -> list[list[float]]:
    """无需模型下载的 hashing vector fallback，用于离线可运行和测试。"""
    vectors: list[list[float]] = []
    for text in texts:
        vector = np.zeros(dimensions, dtype=float)
        for token in TOKEN_RE.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % dimensions
            vector[index] += 1.0
        if not np.any(vector):
            vector[0] = 1.0
        vectors.append(vector.tolist())
    return vectors


def api_embeddings(texts: list[str]) -> list[list[float]]:
    key = os.getenv("RADAR_EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("RADAR_EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL")
    model = os.getenv("RADAR_EMBEDDING_MODEL", "text-embedding-3-small")
    if not key or not base_url:
        raise RuntimeError("未配置 RADAR_EMBEDDING_API_KEY / RADAR_EMBEDDING_BASE_URL")
    batch_size = max(1, int(os.getenv("RADAR_EMBEDDING_BATCH_SIZE", "64")))
    client = OpenAI(api_key=key, base_url=base_url)
    embeddings: list[list[float]] = []
    for offset in range(0, len(texts), batch_size):
        response = client.embeddings.create(input=texts[offset : offset + batch_size], model=model)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings


def sentence_transformer_embeddings(texts: list[str]) -> list[list[float]]:
    """使用 daily arxiv 的 SentenceTransformer 配置生成本地 embedding。"""
    global _LOCAL_ENCODER, _LOCAL_ENCODER_KEY
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "缺少 sentence-transformers。请安装 backend/requirements.txt，或将 RADAR_EMBEDDING_PROVIDER 改为 api/lexical"
        ) from exc

    model_name = os.getenv(
        "RADAR_EMBEDDING_MODEL",
        "jinaai/jina-embeddings-v5-text-nano-retrieval",
    ).strip()
    trust_remote_code = _env_bool("RADAR_EMBEDDING_TRUST_REMOTE_CODE", True)
    encoder_key = (model_name, trust_remote_code)
    if _LOCAL_ENCODER is None or _LOCAL_ENCODER_KEY != encoder_key:
        _LOCAL_ENCODER = SentenceTransformer(model_name, trust_remote_code=trust_remote_code)
        _LOCAL_ENCODER_KEY = encoder_key

    encode_kwargs: dict[str, object] = {
        "task": os.getenv("RADAR_EMBEDDING_TASK", "retrieval").strip() or "retrieval",
    }
    prompt_name = os.getenv("RADAR_EMBEDDING_PROMPT_NAME", "document").strip()
    if prompt_name:
        encode_kwargs["prompt_name"] = prompt_name
    try:
        features = _LOCAL_ENCODER.encode(texts, **encode_kwargs, show_progress_bar=False)
    except TypeError as exc:
        raise RuntimeError(
            "SentenceTransformer 不支持 daily arxiv 的 encode 参数 task/prompt_name，请升级 sentence-transformers"
        ) from exc
    return np.asarray(features).tolist()


def get_embedding_provider():
    provider = os.getenv("RADAR_EMBEDDING_PROVIDER", "local").strip().casefold()
    if provider in {"local", "sentence-transformer", "sentence_transformer"}:
        return sentence_transformer_embeddings
    if provider == "lexical":
        return lexical_embeddings
    if provider == "api":
        return api_embeddings
    raise RuntimeError(f"不支持的 RADAR_EMBEDDING_PROVIDER: {provider}")
