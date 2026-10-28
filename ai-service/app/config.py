"""Local-first configuration. No secrets are required for Phase 1 KPI endpoints."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_SERVICE_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=AI_SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sample_data_dir: Path = REPO_ROOT / "sample-data"
    log_level: str = "INFO"

    def resolved_sample_data_dir(self) -> Path:
        path = self.sample_data_dir
        if not path.is_absolute():
            path = (AI_SERVICE_ROOT / path).resolve()
        return path


def get_settings() -> Settings:
    return Settings()
