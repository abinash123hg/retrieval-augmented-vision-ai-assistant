from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "DocuLens"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen2.5:1.5b"
    ollama_embed_model: str = "nomic-embed-text:latest"

    max_file_size_mb: int = 25
    # Verified against real nomic-embed-text cosine scores on this corpus:
    # relevant chunks measured 0.50-0.77, cross-document noise 0.32-0.49.
    # 0.68 was rejected empirically — it would turn basic facts into "not found".
    top_k_results: int = 4
    min_retrieval_score: float = 0.5
    max_context_characters: int = 12000
    max_sources: int = 2

    upload_dir: str = "app/data/uploads"
    processed_dir: str = "app/data/processed"
    index_dir: str = "app/data/indexes"
    report_dir: str = "app/data/reports"

    tesseract_cmd: str | None = None

    def _resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else BACKEND_ROOT / path

    @property
    def upload_path(self) -> Path:
        return self._resolve(self.upload_dir)

    @property
    def processed_path(self) -> Path:
        return self._resolve(self.processed_dir)

    @property
    def index_path(self) -> Path:
        return self._resolve(self.index_dir)

    @property
    def report_path(self) -> Path:
        return self._resolve(self.report_dir)

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for path in (
            self.upload_path,
            self.processed_path,
            self.index_path,
            self.report_path,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
