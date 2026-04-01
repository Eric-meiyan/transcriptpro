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
    db_path: Path = Path.home() / ".transcriptpro" / "transcriptpro.db"

    # Server
    host: str = "127.0.0.1"
    port: int = 18562  # Random high port for local use

    # Whisper defaults
    default_model: str = "small"
    default_language: str | None = None  # None = auto-detect

    # yt-dlp
    ytdlp_proxy: str | None = None

    # Transcription
    chunk_duration_sec: int = 600  # 10 minutes
    chunk_overlap_sec: int = 30   # 30 seconds overlap

    # Limits (enforced client-side, reference here)
    free_max_duration_sec: int = 1800   # 30 minutes
    standard_max_duration_sec: int = 3600  # 60 minutes
    free_monthly_limit: int = 3
    standard_monthly_limit: int = 100

    def ensure_dirs(self):
        """Create necessary directories."""
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
