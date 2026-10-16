import json
import os
from dataclasses import dataclass, field
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


def load_environment() -> None:
    if os.getenv("SERVICEOS_ENV") != "production":
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def environment_secret(name: str) -> str:
    value, filename = os.getenv(name, ""), os.getenv(f"{name}_FILE", "")
    if value and filename:
        raise ValueError(f"Set {name} or its secret file, not both.")
    if filename:
        try:
            value = Path(filename).read_text(encoding="utf-8").strip()
        except OSError:
            raise ValueError(f"Cannot read secret file for {name}.") from None
    return value


def _values(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    return tuple(part.strip() for part in value.split(",") if part.strip()) if value is not None else default


@dataclass(frozen=True)
class Settings:
    environment: str = "production"
    auth_mode: str = "disabled"
    local_password: str = field(default="", repr=False)
    llm_model: str = ""
    llm_api_key: str = field(default="", repr=False)
    llm_base_url: str = ""
    llm_extra_body: dict = field(default_factory=dict, repr=False)
    llm_timeout_seconds: int = 60
    embedding_model: str = ""
    embedding_api_key: str = field(default="", repr=False)
    embedding_base_url: str = ""
    embedding_provider: str = "openai_compatible"
    embedding_dimensions: int = 1024
    embedding_timeout_seconds: int = 30
    worker_lease_seconds: int = 90
    worker_heartbeat_seconds: int = 20
    worker_max_attempts: int = 5
    evidence_storage_dir: str = ""
    evidence_storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_prefix: str = "evidence"
    mock_action_result: str = "SUCCEEDED"
    allow_container_bootstrap: bool = False
    local_auth_networks: tuple[str, ...] = ("127.0.0.0/8", "::1/128")
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173", "http://127.0.0.1:4173", "http://127.0.0.1:8000",
    )

    def __post_init__(self):
        if self.environment not in ("development", "test", "production"):
            raise ValueError("Unsupported SERVICEOS_ENV.")
        if self.auth_mode not in ("local", "disabled"):
            raise ValueError("Unsupported authentication adapter.")
        if self.environment == "production" and self.auth_mode == "local":
            raise ValueError("Local authentication is forbidden in production.")
        for cidr in self.local_auth_networks:
            network = ip_network(cidr, strict=True)
            if not (network.is_private or network.is_loopback) or network.prefixlen == 0:
                raise ValueError("Local authentication networks must be explicit private networks.")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or "*" in origin:
                raise ValueError("Allowed origins must be exact HTTP(S) origins.")
        if self.evidence_storage_backend not in ("local", "s3"):
            raise ValueError("Unsupported evidence storage backend.")
        if self.worker_heartbeat_seconds >= self.worker_lease_seconds:
            raise ValueError("Worker heartbeat must be shorter than its lease.")
        if self.embedding_dimensions != 1024:
            raise ValueError("Embedding dimensions must be 1024; migration 0017 fixes the vector column width.")
        if self.embedding_provider not in ("openai_compatible", "dashscope_multimodal"):
            raise ValueError("Unsupported embedding provider adapter.")
        if not 5 <= self.embedding_timeout_seconds <= 120:
            raise ValueError("Embedding timeout must stay between 5 and 120 seconds.")

    @property
    def local_auth_enabled(self) -> bool:
        return self.environment in ("development", "test") and self.auth_mode == "local" and bool(self.local_password)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_model and self.llm_api_key and self.llm_base_url)

    @property
    def embedding_configured(self) -> bool:
        return bool(self.embedding_model and self.embedding_api_key and self.embedding_base_url)

    @classmethod
    def from_environment(cls):
        load_environment()
        return cls(
            environment=os.getenv("SERVICEOS_ENV", "production"),
            auth_mode=os.getenv("SERVICEOS_AUTH_MODE", "disabled"),
            local_password=environment_secret("SERVICEOS_LOCAL_AUTH_PASSWORD"),
            llm_model=os.getenv("SERVICEOS_LLM_MODEL", ""),
            llm_api_key=environment_secret("SERVICEOS_LLM_API_KEY"),
            llm_base_url=os.getenv("SERVICEOS_LLM_BASE_URL", "").rstrip("/"),
            llm_extra_body=_llm_extra_body(os.getenv("SERVICEOS_LLM_EXTRA_BODY_JSON", "")),
            llm_timeout_seconds=max(10, min(int(os.getenv("SERVICEOS_LLM_TIMEOUT_SECONDS", "60")), 180)),
            embedding_model=os.getenv("SERVICEOS_EMBEDDING_MODEL", ""),
            embedding_api_key=environment_secret("SERVICEOS_EMBEDDING_API_KEY"),
            embedding_base_url=os.getenv("SERVICEOS_EMBEDDING_BASE_URL", "").rstrip("/"),
            embedding_provider=os.getenv("SERVICEOS_EMBEDDING_PROVIDER", "openai_compatible"),
            embedding_dimensions=int(os.getenv("SERVICEOS_EMBEDDING_DIMENSIONS", "1024")),
            embedding_timeout_seconds=max(5, min(int(os.getenv("SERVICEOS_EMBEDDING_TIMEOUT_SECONDS", "30")), 120)),
            worker_lease_seconds=max(30, min(int(os.getenv("SERVICEOS_WORKER_LEASE_SECONDS", "90")), 600)),
            worker_heartbeat_seconds=max(5, min(int(os.getenv("SERVICEOS_WORKER_HEARTBEAT_SECONDS", "20")), 120)),
            worker_max_attempts=max(1, min(int(os.getenv("SERVICEOS_WORKER_MAX_ATTEMPTS", "5")), 10)),
            evidence_storage_dir=os.getenv("SERVICEOS_EVIDENCE_STORAGE_DIR", ""),
            evidence_storage_backend=os.getenv("SERVICEOS_EVIDENCE_STORAGE_BACKEND", "local"),
            s3_bucket=os.getenv("SERVICEOS_S3_BUCKET", ""),
            s3_region=os.getenv("SERVICEOS_S3_REGION", ""),
            s3_prefix=os.getenv("SERVICEOS_S3_PREFIX", "evidence"),
            mock_action_result=os.getenv("SERVICEOS_MOCK_ACTION_RESULT", "SUCCEEDED"),
            allow_container_bootstrap=os.getenv("SERVICEOS_ALLOW_CONTAINER_BOOTSTRAP") == "1",
            local_auth_networks=_values("SERVICEOS_LOCAL_AUTH_NETWORKS", cls.local_auth_networks),
            allowed_origins=_values("SERVICEOS_ALLOWED_ORIGINS", cls.allowed_origins),
        )


def _llm_extra_body(raw: str) -> dict:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("SERVICEOS_LLM_EXTRA_BODY_JSON must be a JSON object.") from None
    if not isinstance(value, dict):
        raise ValueError("SERVICEOS_LLM_EXTRA_BODY_JSON must be a JSON object.")
    return value
