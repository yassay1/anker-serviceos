import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    environment: str = "production"
    auth_mode: str = "disabled"
    local_password: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: int = 60
    worker_lease_seconds: int = 90
    worker_heartbeat_seconds: int = 20
    worker_max_attempts: int = 5
    evidence_storage_dir: str = ""
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173", "http://127.0.0.1:4173", "http://127.0.0.1:8000",
    )

    @property
    def local_auth_enabled(self) -> bool:
        return self.environment in ("development", "test") and self.auth_mode == "local" and bool(self.local_password)

    @property
    def llm_configured(self) -> bool:
        # Require an explicit destination; never silently send customer content to a default host.
        return bool(self.llm_model and self.llm_api_key and self.llm_base_url)

    @classmethod
    def from_environment(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        return cls(
            environment=os.getenv("SERVICEOS_ENV", "production"),
            auth_mode=os.getenv("SERVICEOS_AUTH_MODE", "disabled"),
            local_password=os.getenv("SERVICEOS_LOCAL_AUTH_PASSWORD", ""),
            llm_model=os.getenv("SERVICEOS_LLM_MODEL", ""),
            llm_api_key=os.getenv("SERVICEOS_LLM_API_KEY", ""),
            llm_base_url=os.getenv("SERVICEOS_LLM_BASE_URL", "").rstrip("/"),
            llm_timeout_seconds=max(10, min(int(os.getenv("SERVICEOS_LLM_TIMEOUT_SECONDS", "60")), 180)),
            worker_lease_seconds=max(30, min(int(os.getenv("SERVICEOS_WORKER_LEASE_SECONDS", "90")), 600)),
            worker_heartbeat_seconds=max(5, min(int(os.getenv("SERVICEOS_WORKER_HEARTBEAT_SECONDS", "20")), 120)),
            worker_max_attempts=max(1, min(int(os.getenv("SERVICEOS_WORKER_MAX_ATTEMPTS", "5")), 10)),
            evidence_storage_dir=os.getenv("SERVICEOS_EVIDENCE_STORAGE_DIR", ""),
        )
