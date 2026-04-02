"""
Main transcription pipeline — orchestrates the 4-layer fallback strategy.

Layer 1: YouTube subtitle extraction (instant, free)
Layer 2: yt-dlp audio download → Whisper local transcription
Layer 3: User manual upload → Whisper local transcription
Layer 4: Groq API cloud transcription (V2, requires user API key)
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from app.config import settings
from app.services.subtitle_extractor import (
    SubtitleResult,
    extract_youtube_subtitles,
)
from app.services.audio_downloader import (
    AudioDownloadResult,
    VideoInfo,
    download_audio,
    get_video_info,
    update_ytdlp,
)
from app.services.whisper_transcriber import (
    TranscriptionResult,
    TranscriptSegment,
    get_transcriber,
)

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    GETTING_INFO = "getting_info"
    CHECKING_SUBTITLES = "checking_subtitles"
    DOWNLOADING_AUDIO = "downloading_audio"
    UPDATING_YTDLP = "updating_ytdlp"
    TRANSCRIBING = "transcribing"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    DOWNLOAD_FAILED = "download_failed"  # Needs manual upload


class TranscriptionSource(str, Enum):
    YOUTUBE_SUBTITLE = "youtube_subtitle"
    WHISPER_LOCAL = "whisper_local"
    MANUAL_UPLOAD = "manual_upload"
    GROQ_API = "groq_api"


@dataclass
class TaskProgress:
    status: TaskStatus
    message: str
    percent: float = 0.0
    current_chunk: int = 0
    total_chunks: int = 0


@dataclass
class TranscriptionOutput:
    segments: list[TranscriptSegment]
    video_info: VideoInfo | None
    language: str
    duration: float
    source: TranscriptionSource
    model_name: str | None = None


# Progress callback type
ProgressCallback = Callable[[TaskProgress], None]


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube video."""
    youtube_patterns = [
        "youtube.com/watch",
        "youtu.be/",
        "youtube.com/shorts/",
        "youtube.com/live/",
        "m.youtube.com/watch",
    ]
    return any(p in url for p in youtube_patterns)


async def transcribe_url(
    url: str,
    language: str | None = None,
    model_name: str = "small",
    on_progress: ProgressCallback | None = None,
) -> TranscriptionOutput:
    """
    Main entry point: transcribe a video from URL.

    Implements the 4-layer fallback strategy.
    """

    def report(status: TaskStatus, message: str, pct: float = 0):
        if on_progress:
            on_progress(TaskProgress(
                status=status, message=message, percent=pct
            ))

    # --- Get video info ---
    report(TaskStatus.GETTING_INFO, "获取视频信息...")

    video_info = await asyncio.to_thread(get_video_info, url)
    if not video_info:
        raise TranscriptionError("无法获取视频信息，请检查 URL 是否正确")

    logger.info(
        f"Video: {video_info.title} ({video_info.duration:.0f}s)"
    )

    # --- Layer 1: Try YouTube subtitles ---
    if is_youtube_url(url):
        report(TaskStatus.CHECKING_SUBTITLES, "检查字幕...", 5)

        sub_result = await asyncio.to_thread(extract_youtube_subtitles, url, language)
        if sub_result and sub_result.segments:
            logger.info(
                f"Layer 1 success: YouTube subtitles "
                f"({sub_result.source}, {sub_result.language})"
            )
            report(TaskStatus.COMPLETED, "字幕提取完成！", 100)

            return TranscriptionOutput(
                segments=[
                    TranscriptSegment(
                        start=s.start, end=s.end, text=s.text
                    )
                    for s in sub_result.segments
                ],
                video_info=video_info,
                language=sub_result.language,
                duration=video_info.duration,
                source=TranscriptionSource.YOUTUBE_SUBTITLE,
            )

        logger.info("Layer 1: No subtitles available, falling back to Layer 2")

    # --- Layer 2: Download audio + Whisper ---
    report(TaskStatus.DOWNLOADING_AUDIO, "下载音频...", 10)

    audio_result = await asyncio.to_thread(download_audio, url)

    # If download fails, try updating yt-dlp and retry once
    if audio_result is None:
        logger.info("Download failed, updating yt-dlp and retrying...")
        report(TaskStatus.UPDATING_YTDLP, "更新下载引擎...", 12)

        if await asyncio.to_thread(update_ytdlp):
            report(TaskStatus.DOWNLOADING_AUDIO, "重试下载...", 15)
            audio_result = await asyncio.to_thread(download_audio, url)

    if audio_result is None:
        # Layer 2 failed — signal that manual upload is needed
        logger.warning("Layer 2 failed: audio download unsuccessful")
        report(
            TaskStatus.DOWNLOAD_FAILED,
            "自动下载失败，请手动下载视频/音频后拖入应用",
            0,
        )
        raise DownloadFailedError(
            "音频下载失败。可能是 YouTube 限制或网络问题。\n"
            "请尝试手动下载视频后拖入应用。"
        )

    # Whisper transcription
    report(TaskStatus.TRANSCRIBING, "正在转录...", 20)

    try:
        transcriber = await asyncio.to_thread(get_transcriber, model_name)

        def whisper_progress(current, total, pct):
            # Map Whisper progress to 20-95% range
            mapped_pct = 20 + (pct / 100) * 75
            report(
                TaskStatus.TRANSCRIBING,
                f"转录中... ({current}/{total} 段)",
                mapped_pct,
            )

        result = await asyncio.to_thread(
            transcriber.transcribe,
            audio_result.audio_path,
            language,
            whisper_progress,
        )

        logger.info(
            f"Layer 2 success: Whisper transcription "
            f"({len(result.segments)} segments, {result.language})"
        )
        report(TaskStatus.COMPLETED, "转录完成！", 100)

        return TranscriptionOutput(
            segments=result.segments,
            video_info=video_info,
            language=result.language,
            duration=result.duration,
            source=TranscriptionSource.WHISPER_LOCAL,
            model_name=result.model_name,
        )

    finally:
        # Clean up temp audio file
        _cleanup_temp(audio_result.audio_path)


async def transcribe_local_file(
    file_path: Path,
    language: str | None = None,
    model_name: str = "small",
    on_progress: ProgressCallback | None = None,
) -> TranscriptionOutput:
    """
    Transcribe a local audio/video file (Layer 3).

    Works completely offline once model is downloaded.
    """

    def report(status: TaskStatus, message: str, pct: float = 0):
        if on_progress:
            on_progress(TaskProgress(
                status=status, message=message, percent=pct
            ))

    if not file_path.exists():
        raise TranscriptionError(f"文件不存在: {file_path}")

    # Extract audio from video if needed
    audio_path = file_path
    needs_cleanup = False

    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
    if file_path.suffix.lower() in video_extensions:
        report(TaskStatus.DOWNLOADING_AUDIO, "提取音频...", 5)
        audio_path = await asyncio.to_thread(_extract_audio_from_video, file_path)
        needs_cleanup = True

    try:
        report(TaskStatus.TRANSCRIBING, "正在转录...", 10)

        transcriber = await asyncio.to_thread(get_transcriber, model_name)

        def whisper_progress(current, total, pct):
            mapped_pct = 10 + (pct / 100) * 85
            report(
                TaskStatus.TRANSCRIBING,
                f"转录中... ({current}/{total} 段)",
                mapped_pct,
            )

        result = await asyncio.to_thread(
            transcriber.transcribe,
            audio_path,
            language,
            whisper_progress,
        )

        report(TaskStatus.COMPLETED, "转录完成！", 100)

        return TranscriptionOutput(
            segments=result.segments,
            video_info=VideoInfo(
                id=file_path.stem,
                title=file_path.name,
                duration=result.duration,
                thumbnail=None,
                channel=None,
                upload_date=None,
            ),
            language=result.language,
            duration=result.duration,
            source=TranscriptionSource.MANUAL_UPLOAD,
            model_name=result.model_name,
        )

    finally:
        if needs_cleanup:
            _cleanup_temp(audio_path)


def _extract_audio_from_video(video_path: Path) -> Path:
    """Extract audio from video file using ffmpeg."""
    import subprocess

    audio_path = settings.temp_dir / f"{video_path.stem}_audio.wav"
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            str(audio_path),
        ],
        capture_output=True,
        timeout=300,
        check=True,
    )

    return audio_path


def _cleanup_temp(path: Path):
    """Remove temporary file."""
    try:
        if path.exists():
            path.unlink()
            logger.debug(f"Cleaned up temp file: {path}")
    except OSError as e:
        logger.warning(f"Failed to clean up {path}: {e}")


class TranscriptionError(Exception):
    """General transcription error."""
    pass


class DownloadFailedError(TranscriptionError):
    """Audio download failed — user should upload manually."""
    pass
