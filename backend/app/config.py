"""Application configuration."""

import os
from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    """App settings."""

    # Paths
    app_data_dir: Path = Path.home() / ".transcriptpro"
    models_dir: Path = Path.home() / ".transcriptpro" / "models"
    temp_dir: Path = Path.home() / ".transcriptpro" / "temp"

    # Server
    host: str = "0.0.0.0"
    port: int = 18562

    # Security — only accept requests with this secret
    api_secret: str = os.getenv("API_SECRET", "")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Whisper defaults
    default_model: str = os.getenv("WHISPER_MODEL", "small")
    default_language: str | None = None  # None = auto-detect

    # yt-dlp proxy (IPRoyal residential proxy)
    ytdlp_proxy: str | None = os.getenv("PROXY_URL", None)

    # Transcription
    chunk_duration_sec: int = 600  # 10 minutes
    chunk_overlap_sec: int = 30   # 30 seconds overlap

    # Worker
    worker_concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "4"))

    # Result cache TTL
    result_ttl_seconds: int = 86400  # 24 hours

    def ensure_dirs(self):
        """Create necessary directories."""
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
