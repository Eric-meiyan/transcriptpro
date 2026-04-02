"""Layer 2: Download audio stream from YouTube via yt-dlp."""

import json
import logging
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    id: str
    title: str
    duration: float  # seconds
    thumbnail: str | None
    channel: str | None
    upload_date: str | None


@dataclass
class AudioDownloadResult:
    audio_path: Path
    video_info: VideoInfo


def get_video_info(url: str) -> VideoInfo | None:
    """Get video metadata without downloading."""
    try:
        cmd = [
            "yt-dlp",
            "--print-json",
            "--skip-download",
            "--no-warnings",
        ]

        # Use proxy if configured (YouTube blocks data center IPs)
        if settings.ytdlp_proxy:
            cmd.extend(["--proxy", settings.ytdlp_proxy])

        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"yt-dlp info failed: {result.stderr}")
            return None

        info = json.loads(result.stdout)
        return VideoInfo(
            id=info.get("id", "unknown"),
            title=info.get("title", "Untitled"),
            duration=float(info.get("duration", 0)),
            thumbnail=info.get("thumbnail"),
            channel=info.get("channel") or info.get("uploader"),
            upload_date=info.get("upload_date"),
        )

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp info timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
        return None


def download_audio(
    url: str,
    output_dir: Path | None = None,
    proxy: str | None = None,
) -> AudioDownloadResult | None:
    """
    Download audio stream only (not full video).

    YouTube stores video and audio separately (DASH format).
    yt-dlp can download just the audio stream: ~5-20MB per hour
    vs ~500MB-2GB for full video.
    """
    if output_dir is None:
        output_dir = settings.temp_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get video info first
        video_info = get_video_info(url)
        if not video_info:
            return None

        output_path = output_dir / f"{video_info.id}.wav"

        cmd = [
            "yt-dlp",
            # Download best audio only (no video)
            "-f", "bestaudio",
            # Extract audio and convert to WAV (16kHz mono for Whisper)
            "-x",
            "--audio-format", "wav",
            "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
            # Output path
            "-o", str(output_dir / f"{video_info.id}.%(ext)s"),
            # No playlist
            "--no-playlist",
            # Quiet
            "--no-warnings",
        ]

        if proxy:
            cmd.extend(["--proxy", proxy])
        elif settings.ytdlp_proxy:
            cmd.extend(["--proxy", settings.ytdlp_proxy])

        cmd.append(url)

        logger.info(f"Downloading audio for: {video_info.title}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
        )

        if result.returncode != 0:
            logger.error(f"yt-dlp download failed: {result.stderr}")
            return None

        # yt-dlp might output with different extension during processing
        # Find the actual output file
        if not output_path.exists():
            # Check for the file before post-processing
            for ext in ["wav", "m4a", "webm", "opus"]:
                alt_path = output_dir / f"{video_info.id}.{ext}"
                if alt_path.exists():
                    output_path = alt_path
                    break

        if not output_path.exists():
            logger.error(f"Audio file not found after download")
            return None

        logger.info(
            f"Audio downloaded: {output_path} "
            f"({output_path.stat().st_size / 1024 / 1024:.1f} MB)"
        )

        return AudioDownloadResult(
            audio_path=output_path,
            video_info=video_info,
        )

    except subprocess.TimeoutExpired:
        logger.error("Audio download timed out (5 min)")
        return None
    except Exception as e:
        logger.error(f"Audio download failed: {e}")
        return None


def update_ytdlp() -> bool:
    """Update yt-dlp to latest version."""
    try:
        logger.info("Updating yt-dlp...")
        result = subprocess.run(
            ["pip", "install", "-U", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("yt-dlp updated successfully")
            return True
        else:
            logger.error(f"yt-dlp update failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"yt-dlp update error: {e}")
        return False


def check_ytdlp_update_available() -> bool:
    """Check if a newer version of yt-dlp is available."""
    try:
        result = subprocess.run(
            ["pip", "index", "versions", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # Simple heuristic: if current != latest, update available
        current = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and current.returncode == 0:
            return current.stdout.strip() not in result.stdout
        return False
    except Exception:
        return False
