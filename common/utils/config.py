"""
Centralized, validated runtime configuration for the PBAI service.
It provides explicit defaults, environment parsing, and strict value checks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when runtime configuration is missing or invalid."""


def _read_str(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, "").strip()
    return value if value else default


def _read_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _read_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a float, got {raw!r}") from exc


def _read_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean (true/false), got {raw!r}")


def _resolve_path(raw: str, *, default: Path, base: Path) -> Path:
    value = raw.strip()
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _read_index_batch_size(env: Mapping[str, str], default: int) -> int:
    for name in ("PBAI_INDEX_BATCH_SIZE", "INDEX_BATCH_SIZE"):
        raw = env.get(name, "").strip()
        if raw:
            try:
                return int(raw)
            except ValueError as exc:
                raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    return default


@dataclass(frozen=True)
class Settings:
    session_timeout: int
    audit_log_dir: Path
    model_type: str
    max_tokens: int
    conversation_history_turns: int
    temperature: float
    api_key: str
    storage_root: Path
    ref_base: Path
    group_access_file: Path
    master_users_file: Path
    allowed_origins: list[str]
    port: int
    chunk_mode: str
    chunk_min_chars: int
    chunk_target_chars: int
    chunk_max_chars: int
    chunk_overlap_sentences: int
    chunk_sim_threshold: float
    index_batch_size: int
    llm_loader_url: str
    model_id: str
    internal_secret: str
    llm_client_connect_timeout: float
    llm_client_read_timeout: float
    file_audit_format: str
    meta_display: str
    chunk_preserve_markers: bool
    pdf_cross_page: bool
    query_synonym_file: str
    rrf_weight_word: float
    rrf_weight_char: float
    rrf_weight_bm25: float
    section_title_boost: float
    rerank_enabled: bool
    rerank_candidates: int
    rerank_phrase_weight: float
    rerank_density_weight: float
    rerank_title_weight: float
    audit_source_text: bool
    html_single_chunk_max_chars: int
    sys_log_dur: int
    # CAS / JWT settings
    jwt_verify: bool
    jwt_algorithm: str
    jwt_secret: str
    jwt_public_key_file: str


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STORAGE_ROOT = _PROJECT_ROOT.parent / "storage_volume"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = env if env is not None else os.environ

    pbai_env = source.get("PBAI_ENV", "").strip()
    if pbai_env == "008":
        storage_root_raw = source.get("PBAI_STORAGE_ROOT_008", "").strip()
        llm_loader_url = source.get("LLM_LOADER_URL_008", "http://localhost:8501").strip()
    elif pbai_env == "OpenShift":
        storage_root_raw = source.get("PBAI_STORAGE_ROOT_OPENSHIFT", "").strip()
        llm_loader_url = source.get("LLM_LOADER_URL_OPENSHIFT", "http://llm-loader.askpbai.svc.cluster.local:8501").strip()
    else:
        storage_root_raw = source.get("PBAI_STORAGE_ROOT", "").strip()
        llm_loader_url = source.get("LLM_LOADER_URL", "http://localhost:8501").strip()
    storage_root = _resolve_path(
        storage_root_raw,
        default=_DEFAULT_STORAGE_ROOT,
        base=_PROJECT_ROOT,
    )

    ref_base = storage_root / "data" / "reference"
    group_access_file = _PROJECT_ROOT / "common" / "utils" / "login_auth" / "group_access.json"
    master_users_file = storage_root / "access_control" / "master_users.json"
    audit_log_dir = storage_root / "logs"

    allowed_origins_raw = _read_str(
        source,
        "POLICY_RAG_ALLOWED_ORIGINS",
        "http://localhost:3000",
    )
    allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]

    jwt_algorithm_raw = _read_str(source, "PBAI_JWT_ALGORITHM", "HS256")
    if jwt_algorithm_raw not in {"HS256", "RS256", "RS512"}:
        raise ConfigError(f"PBAI_JWT_ALGORITHM must be 'HS256', 'RS256', or 'RS512', got {jwt_algorithm_raw!r}")

    settings = Settings(
        session_timeout=_read_int(source, "PBAI_SESSION_TIMEOUT", 1800),
        audit_log_dir=audit_log_dir,
        model_type=_read_str(source, "PBAI_MODEL_TYPE", "Qwen2.5"),
        max_tokens=_read_int(source, "PBAI_MAX_TOKENS", 4096),
        conversation_history_turns=_read_int(source, "PBAI_CONVERSATION_HISTORY_TURNS", 0),
        temperature=_read_float(source, "PBAI_TEMPERATURE", 0.3),
        api_key=_read_str(source, "POLICY_RAG_API_KEY", "changeme-secret-key"),
        storage_root=storage_root,
        ref_base=ref_base,
        group_access_file=group_access_file,
        master_users_file=master_users_file,
        allowed_origins=allowed_origins,
        port=_read_int(source, "POLICY_RAG_PORT", 8502),
        chunk_mode=_read_str(source, "PBAI_CHUNK_MODE", "fixed"),
        chunk_min_chars=_read_int(source, "PBAI_CHUNK_MIN_CHARS", 900),
        chunk_target_chars=_read_int(source, "PBAI_CHUNK_TARGET_CHARS", 1600),
        chunk_max_chars=_read_int(source, "PBAI_CHUNK_MAX_CHARS", 2400),
        chunk_overlap_sentences=_read_int(source, "PBAI_CHUNK_OVERLAP_SENTENCES", 2),
        chunk_sim_threshold=_read_float(source, "PBAI_CHUNK_SIM_THRESHOLD", 0.1),
        index_batch_size=_read_index_batch_size(source, default=20),
        llm_loader_url=llm_loader_url,
        model_id=_read_str(source, "PBAI_MODEL_ID", "local-model"),
        internal_secret=_read_str(source, "LLM_INTERNAL_SECRET", ""),
        llm_client_connect_timeout=_read_float(source, "LLM_CLIENT_CONNECT_TIMEOUT", 5.0),
        llm_client_read_timeout=_read_float(source, "LLM_CLIENT_READ_TIMEOUT", 120.0),
        file_audit_format=_read_str(source, "PBAI_FILE_AUDIT_FORMAT", "day"),
        meta_display=_read_str(source, "PBAI_META_DISPLAY", "showall"),
        chunk_preserve_markers=_read_bool(source, "PBAI_CHUNK_PRESERVE_MARKERS", True),
        pdf_cross_page=_read_bool(source, "PBAI_PDF_CROSS_PAGE", True),
        query_synonym_file=_read_str(source, "PBAI_QUERY_SYNONYM_FILE", ""),
        rrf_weight_word=_read_float(source, "PBAI_RRF_WEIGHT_WORD", 1.0),
        rrf_weight_char=_read_float(source, "PBAI_RRF_WEIGHT_CHAR", 0.5),
        rrf_weight_bm25=_read_float(source, "PBAI_RRF_WEIGHT_BM25", 1.0),
        section_title_boost=_read_float(source, "PBAI_SECTION_TITLE_BOOST", 1.2),
        rerank_enabled=_read_bool(source, "PBAI_RERANK_ENABLED", True),
        rerank_candidates=_read_int(source, "PBAI_RERANK_CANDIDATES", 20),
        rerank_phrase_weight=_read_float(source, "PBAI_RERANK_PHRASE_WEIGHT", 0.3),
        rerank_density_weight=_read_float(source, "PBAI_RERANK_DENSITY_WEIGHT", 0.5),
        rerank_title_weight=_read_float(source, "PBAI_RERANK_TITLE_WEIGHT", 0.2),
        audit_source_text=_read_bool(source, "PBAI_AUDIT_SOURCE_TEXT", False),
        html_single_chunk_max_chars=_read_int(source, "PBAI_HTML_SINGLE_CHUNK_MAX_CHARS", 15000),
        sys_log_dur=_read_int(source, "PBAI_SYS_LOG_DUR", 1),
        jwt_verify=_read_bool(source, "PBAI_JWT_VERIFY", False),
        jwt_algorithm=jwt_algorithm_raw,
        jwt_secret=_read_str(source, "PBAI_JWT_SECRET", ""),
        jwt_public_key_file=_read_str(source, "PBAI_JWT_PUBLIC_KEY_FILE", ""),
    )

    if settings.session_timeout <= 0:
        raise ConfigError(f"PBAI_SESSION_TIMEOUT must be > 0, got {settings.session_timeout}")
    if settings.max_tokens <= 0:
        raise ConfigError(f"PBAI_MAX_TOKENS must be > 0, got {settings.max_tokens}")
    if settings.conversation_history_turns < 0:
        raise ConfigError(
            f"PBAI_CONVERSATION_HISTORY_TURNS must be >= 0, got {settings.conversation_history_turns}"
        )
    if not (0.0 <= settings.temperature <= 2.0):
        raise ConfigError(f"PBAI_TEMPERATURE must be between 0.0 and 2.0, got {settings.temperature}")
    if not settings.allowed_origins:
        raise ConfigError("POLICY_RAG_ALLOWED_ORIGINS must contain at least one non-empty origin")
    if not (1 <= settings.port <= 65535):
        raise ConfigError(f"POLICY_RAG_PORT must be between 1 and 65535, got {settings.port}")
    if settings.chunk_mode not in {"fixed", "hybrid", "filetype"}:
        raise ConfigError(f"PBAI_CHUNK_MODE must be 'fixed', 'hybrid', or 'filetype', got {settings.chunk_mode!r}")
    if not (0 <= settings.chunk_overlap_sentences <= 5):
        raise ConfigError(
            "PBAI_CHUNK_OVERLAP_SENTENCES must be between 0 and 5, "
            f"got {settings.chunk_overlap_sentences}"
        )
    if not (settings.chunk_min_chars <= settings.chunk_target_chars <= settings.chunk_max_chars):
        raise ConfigError(
            "Chunk size ordering invalid: "
            f"PBAI_CHUNK_MIN_CHARS ({settings.chunk_min_chars}) <= "
            f"PBAI_CHUNK_TARGET_CHARS ({settings.chunk_target_chars}) <= "
            f"PBAI_CHUNK_MAX_CHARS ({settings.chunk_max_chars}) is required"
        )
    if not (0.0 <= settings.chunk_sim_threshold <= 1.0):
        raise ConfigError(
            f"PBAI_CHUNK_SIM_THRESHOLD must be between 0.0 and 1.0, got {settings.chunk_sim_threshold}"
        )
    if settings.index_batch_size < 1:
        raise ConfigError(f"PBAI_INDEX_BATCH_SIZE must be >= 1, got {settings.index_batch_size}")
    if settings.llm_client_connect_timeout <= 0:
        raise ConfigError(
            "LLM_CLIENT_CONNECT_TIMEOUT must be > 0, "
            f"got {settings.llm_client_connect_timeout}"
        )
    if settings.llm_client_read_timeout <= 0:
        raise ConfigError(
            f"LLM_CLIENT_READ_TIMEOUT must be > 0, got {settings.llm_client_read_timeout}"
        )
    if settings.file_audit_format not in {"day", "month"}:
        raise ConfigError(f"PBAI_FILE_AUDIT_FORMAT must be 'day' or 'month', got {settings.file_audit_format!r}")
    if settings.rrf_weight_word < 0:
        raise ConfigError(f"PBAI_RRF_WEIGHT_WORD must be >= 0, got {settings.rrf_weight_word}")
    if settings.rrf_weight_char < 0:
        raise ConfigError(f"PBAI_RRF_WEIGHT_CHAR must be >= 0, got {settings.rrf_weight_char}")
    if settings.rrf_weight_bm25 < 0:
        raise ConfigError(f"PBAI_RRF_WEIGHT_BM25 must be >= 0, got {settings.rrf_weight_bm25}")
    if settings.section_title_boost < 1.0:
        raise ConfigError(f"PBAI_SECTION_TITLE_BOOST must be >= 1.0, got {settings.section_title_boost}")
    if settings.rerank_candidates < 1:
        raise ConfigError(f"PBAI_RERANK_CANDIDATES must be >= 1, got {settings.rerank_candidates}")
    if settings.html_single_chunk_max_chars < 1:
        raise ConfigError(
            f"PBAI_HTML_SINGLE_CHUNK_MAX_CHARS must be >= 1, got {settings.html_single_chunk_max_chars}"
        )
    if settings.sys_log_dur < 1:
        raise ConfigError(f"PBAI_SYS_LOG_DUR must be >= 1, got {settings.sys_log_dur}")

    return settings


SETTINGS = load_settings()

SESSION_TIMEOUT = SETTINGS.session_timeout
MASTER_USERS_FILE = SETTINGS.master_users_file
ALLOWED_ORIGINS = SETTINGS.allowed_origins
PORT = SETTINGS.port
GROUPS = ["general"]

# -- Derived storage paths (canonical source: common.utils.paths) ----------

AUDIT_LOG_DIR = SETTINGS.audit_log_dir
FILE_AUDIT_FORMAT = SETTINGS.file_audit_format
STORAGE_ROOT = SETTINGS.storage_root
SYS_LOG_DIR = SETTINGS.audit_log_dir / "system" / "policy_helper"
SYS_LOG_DUR = SETTINGS.sys_log_dur

REF_BASE = SETTINGS.ref_base
REF_DIRS = {g: REF_BASE / g for g in GROUPS}
DB_PATHS = {g: REF_BASE / g / "policy.sqlite" for g in GROUPS}

STAGING_DIR = REF_BASE / "staging"
STAGING_DB_PATH = STAGING_DIR / "staging.sqlite"

DELETED_DIR = REF_BASE / "deleted"
DELETED_DB_PATH = DELETED_DIR / "deleted.sqlite"

GROUP_ACCESS_FILE = SETTINGS.group_access_file

# -- CAS / JWT constants -----------------------------------------------------

JWT_VERIFY = SETTINGS.jwt_verify
JWT_ALGORITHM = SETTINGS.jwt_algorithm
JWT_SECRET = SETTINGS.jwt_secret
JWT_PUBLIC_KEY_FILE = SETTINGS.jwt_public_key_file
