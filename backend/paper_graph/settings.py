"""本地应用设置与 `.env` 持久化。"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values, set_key, unset_key


SETTING_DEFAULTS: dict[str, str] = {
    "LLM_BASE_URL": "https://api.openai.com/v1",
    "LLM_MODEL": "gpt-5.5",
    "LLM_PROVIDER_TYPE": "openai_legacy",
    "LLM_CAPABILITIES": "",
    "LLM_MAX_CONTEXT_SIZE": "128000",
    "RADAR_EMBEDDING_PROVIDER": "local",
    "RADAR_EMBEDDING_MODEL": "jinaai/jina-embeddings-v5-text-nano-retrieval",
    "RADAR_EMBEDDING_TASK": "retrieval",
    "RADAR_EMBEDDING_PROMPT_NAME": "document",
    "RADAR_EMBEDDING_TRUST_REMOTE_CODE": "true",
    "RADAR_EMBEDDING_BATCH_SIZE": "64",
    "RADAR_EMBEDDING_BASE_URL": "",
    "RADAR_LLM_ENABLED": "true",
    "RADAR_LLM_REQUIRED": "false",
    "RADAR_DEBUG": "false",
    "RADAR_EMAIL_SENDER": "",
    "RADAR_EMAIL_RECEIVER": "",
    "RADAR_SMTP_HOST": "",
    "RADAR_SMTP_PORT": "465",
    "RADAR_SMTP_SSL": "true",
    "OPENREVIEW_EMAIL": "",
    "EXPLORE_DAY_OFFSET": "1",
    "EXPLORE_ARXIV_ENABLED": "true",
    "EXPLORE_HF_DAILY_ENABLED": "true",
    "EXPLORE_HF_TRENDING_ENABLED": "true",
    "EXPLORE_HF_TRENDING_MAX_AGE_DAYS": "30",
    "EXPLORE_INCLUDE_HISTORICAL_MILESTONES": "false",
    "EXPLORE_WATCHED_AUTHORS_ENABLED": "true",
    "EXPLORE_WATCHED_AUTHORS": (
        "Dan Alistarh|IST Austria,Song Han|MIT HAN Lab,"
        "Markus Nagel|Qualcomm AI Research,Mart van Baalen|Qualcomm AI Research,"
        "Yelysei Bondarenko|Qualcomm AI Research,Marios Fournarakis|Qualcomm AI Research,"
        "Andrey Kuzmin|Qualcomm AI Research,Arash Behboodi|Qualcomm AI Research,"
        "Babak Ehteshami Bejnordi|Qualcomm AI Research,"
        "Tijmen Blankevoort|Qualcomm AI Research (alumni),"
        "Christos Louizos|Qualcomm AI Research (alumni)"
    ),
    "EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS": "7",
    "EXPLORE_OPENREVIEW_ENABLED": "true",
    "EXPLORE_OPENREVIEW_WINDOW_DAYS": "7",
    "EXPLORE_OPENREVIEW_MAX_PAGES": "5",
    "EXPLORE_OPENREVIEW_VENUES": (
        "ICLR.cc/{year}/Conference,ICML.cc/{year}/Conference,"
        "NeurIPS.cc/{year}/Conference,MLSys.org/{year}/Conference,"
        "AAAI.org/{year}/Conference,aclweb.org/ACL/{year}/Conference,"
        "EMNLP/{year}/Conference"
    ),
}

SECRET_SETTINGS = frozenset(
    {
        "LLM_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
        "RADAR_EMBEDDING_API_KEY",
        "RADAR_EMAIL_PASSWORD",
        "OPENREVIEW_PASSWORD",
    }
)

ALLOWED_SETTINGS = frozenset(SETTING_DEFAULTS) | SECRET_SETTINGS


def _current_values(env_path: Path) -> dict[str, str]:
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    return {
        name: os.environ.get(name, file_values.get(name) or SETTING_DEFAULTS.get(name, ""))
        for name in ALLOWED_SETTINGS
    }


def get_app_settings(env_path: Path) -> dict:
    """返回非敏感值与 secret 配置状态，不返回 secret 明文。"""
    values = _current_values(env_path)
    return {
        "values": {
            name: values[name]
            for name in sorted(SETTING_DEFAULTS)
        },
        "secrets": {
            name: bool(values[name].strip())
            for name in sorted(SECRET_SETTINGS)
        },
    }


def update_app_settings(
    env_path: Path,
    values: Mapping[str, object],
    secrets: Mapping[str, object] | None = None,
    clear_secrets: list[str] | None = None,
) -> dict:
    """更新白名单内设置；空 secret 表示保留旧值。"""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.touch(exist_ok=True)
    secret_values = secrets or {}
    clear = set(clear_secrets or [])
    unknown = (set(values) | set(secret_values) | clear) - ALLOWED_SETTINGS
    if unknown:
        raise ValueError(f"不支持的设置项: {', '.join(sorted(unknown))}")
    invalid_secret_names = (set(secret_values) | clear) - SECRET_SETTINGS
    if invalid_secret_names:
        raise ValueError(f"非 secret 设置不能按 secret 更新: {', '.join(sorted(invalid_secret_names))}")

    for name, raw in values.items():
        if name in SECRET_SETTINGS:
            raise ValueError(f"secret 设置必须放在 secrets 字段: {name}")
        value = str(raw).strip()
        set_key(str(env_path), name, value, quote_mode="auto")
        os.environ[name] = value

    for name, raw in secret_values.items():
        value = str(raw).strip()
        if not value:
            continue
        set_key(str(env_path), name, value, quote_mode="always")
        os.environ[name] = value

    for name in clear:
        unset_key(str(env_path), name)
        os.environ.pop(name, None)

    return get_app_settings(env_path)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


def env_authors(name: str, default: str) -> list[tuple[str, str]]:
    """读取“姓名|机构”格式的关注作者名单。"""
    authors: list[tuple[str, str]] = []
    for item in env_list(name, default):
        author, separator, affiliation = item.partition("|")
        author = author.strip()
        if author:
            authors.append((author, affiliation.strip() if separator else ""))
    return authors


def get_explore_runtime_config() -> dict:
    return {
        "arxiv_enabled": env_bool("EXPLORE_ARXIV_ENABLED", True),
        "hf_daily_enabled": env_bool("EXPLORE_HF_DAILY_ENABLED", True),
        "hf_trending_enabled": env_bool("EXPLORE_HF_TRENDING_ENABLED", True),
        "hf_trending_max_age_days": env_int(
            "EXPLORE_HF_TRENDING_MAX_AGE_DAYS", 30, minimum=0, maximum=3650
        ),
        "include_historical_milestones": env_bool(
            "EXPLORE_INCLUDE_HISTORICAL_MILESTONES", False
        ),
        "watched_authors_enabled": env_bool("EXPLORE_WATCHED_AUTHORS_ENABLED", True),
        "watched_authors": env_authors(
            "EXPLORE_WATCHED_AUTHORS", SETTING_DEFAULTS["EXPLORE_WATCHED_AUTHORS"]
        ),
        "watched_authors_window_days": env_int(
            "EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS", 7, minimum=1, maximum=365
        ),
        "openreview_enabled": env_bool("EXPLORE_OPENREVIEW_ENABLED", True),
        "openreview_window_days": env_int(
            "EXPLORE_OPENREVIEW_WINDOW_DAYS", 7, minimum=1, maximum=365
        ),
        "openreview_max_pages": env_int(
            "EXPLORE_OPENREVIEW_MAX_PAGES", 5, minimum=1, maximum=100
        ),
        "openreview_venues": env_list(
            "EXPLORE_OPENREVIEW_VENUES", SETTING_DEFAULTS["EXPLORE_OPENREVIEW_VENUES"]
        ),
    }


def explore_target_date(now: datetime | None = None) -> date:
    """返回最新完整扫描日；默认上一 UTC 日，与参考仓库 daily.sh 一致。"""
    fixed = os.getenv("EXPLORE_TARGET_DATE", "").strip()
    if fixed:
        return date.fromisoformat(fixed)
    current = now or datetime.now(UTC)
    offset = env_int("EXPLORE_DAY_OFFSET", 1, minimum=0, maximum=3650)
    return (current.astimezone(UTC) - timedelta(days=offset)).date()
