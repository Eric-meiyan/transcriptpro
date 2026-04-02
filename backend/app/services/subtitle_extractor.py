"""Layer 1: Extract YouTube subtitles via yt-dlp (fastest, free)."""

import glob
import json
import logging
import os
import subprocess
import re
import tempfile
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SubtitleSegment:
    start: float  # seconds
    end: float
    text: str


@dataclass
class SubtitleResult:
    segments: list[SubtitleSegment]
    language: str
    source: str  # "youtube_manual" | "youtube_auto"


def extract_youtube_subtitles(
    url: str,
    language: str | None = None,
) -> SubtitleResult | None:
    """
    Try to extract subtitles from YouTube video.

    Priority:
    1. Manual (human-uploaded) subtitles in requested language
    2. Auto-generated subtitles in requested language
    3. Manual subtitles in any language
    4. Auto-generated subtitles in any language

    Returns None if no subtitles available.
    """
    try:
        # First, get video info including subtitle metadata
        cmd = ["yt-dlp", "--dump-json", "--skip-download"]
        if settings.ytdlp_proxy:
            cmd.extend(["--proxy", settings.ytdlp_proxy])
        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 min (proxy is slower)
        )

        if result.returncode != 0:
            logger.warning(f"yt-dlp dump-json failed: {result.stderr}")
            return None

        info = json.loads(result.stdout)
        manual_subs = info.get("subtitles", {})
        auto_subs = info.get("automatic_captions", {})

        # Determine which subtitle to download
        sub_lang, sub_source = _pick_subtitle(manual_subs, auto_subs, language)
        if not sub_lang:
            logger.info(f"No subtitles available for {url}")
            return None

        # Download the subtitle
        is_auto = sub_source == "youtube_auto"
        segments = _download_subtitle(url, sub_lang, is_auto)

        if not segments:
            return None

        return SubtitleResult(
            segments=segments,
            language=sub_lang,
            source=sub_source,
        )

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp subtitle extraction timed out")
        return None
    except Exception as e:
        logger.error(f"Subtitle extraction failed: {e}")
        return None


def _pick_subtitle(
    manual_subs: dict,
    auto_subs: dict,
    preferred_lang: str | None,
) -> tuple[str | None, str | None]:
    """Pick the best available subtitle track."""

    if preferred_lang:
        # Check manual first, then auto
        if preferred_lang in manual_subs:
            return preferred_lang, "youtube_manual"
        if preferred_lang in auto_subs:
            return preferred_lang, "youtube_auto"

    # Fallback: any manual subtitle
    if manual_subs:
        # Prefer English if available
        if "en" in manual_subs:
            return "en", "youtube_manual"
        lang = next(iter(manual_subs))
        return lang, "youtube_manual"

    # Fallback: any auto subtitle
    if auto_subs:
        if preferred_lang and preferred_lang in auto_subs:
            return preferred_lang, "youtube_auto"
        if "en" in auto_subs:
            return "en", "youtube_auto"
        lang = next(iter(auto_subs))
        return lang, "youtube_auto"

    return None, None


def _download_subtitle(
    url: str,
    lang: str,
    is_auto: bool,
) -> list[SubtitleSegment]:
    """Download and parse subtitle file."""
    try:
        sub_flag = "--write-auto-subs" if is_auto else "--write-subs"
        cmd = [
            "yt-dlp",
            sub_flag,
            "--sub-langs", lang,
            "--sub-format", "json3",
            "--skip-download",
            "-o", "/tmp/tp_sub_%(id)s",
        ]
        if settings.ytdlp_proxy:
            cmd.extend(["--proxy", settings.ytdlp_proxy])
        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 min (proxy is slower)
        )

        # Find the downloaded subtitle file
        sub_files = glob.glob(f"/tmp/tp_sub_*.{lang}.json3")
        if not sub_files:
            # Try vtt format as fallback
            return _download_subtitle_vtt(url, lang, is_auto)

        with open(sub_files[0], "r") as f:
            data = json.load(f)

        segments = []
        for event in data.get("events", []):
            start_ms = event.get("tStartMs", 0)
            duration_ms = event.get("dDurationMs", 0)
            segs = event.get("segs", [])
            text = "".join(s.get("utf8", "") for s in segs).strip()
            if text and text != "\n":
                segments.append(SubtitleSegment(
                    start=start_ms / 1000.0,
                    end=(start_ms + duration_ms) / 1000.0,
                    text=text,
                ))

        # Cleanup temp files
        for f in sub_files:
            try:
                os.remove(f)
            except OSError:
                pass

        return segments

    except Exception as e:
        logger.error(f"Subtitle download failed: {e}")
        return []


def _download_subtitle_vtt(
    url: str,
    lang: str,
    is_auto: bool,
) -> list[SubtitleSegment]:
    """Fallback: download VTT format and parse."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_flag = "--write-auto-subs" if is_auto else "--write-subs"
        cmd = [
            "yt-dlp",
            sub_flag,
            "--sub-langs", lang,
            "--sub-format", "vtt",
            "--skip-download",
            "-o", os.path.join(tmpdir, "%(id)s"),
        ]
        if settings.ytdlp_proxy:
            cmd.extend(["--proxy", settings.ytdlp_proxy])
        cmd.append(url)

        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 min (proxy is slower)
        )

        # Find VTT file
        vtt_files = glob.glob(os.path.join(tmpdir, f"*.{lang}.vtt"))
        if not vtt_files:
            return []

        return _parse_vtt(vtt_files[0])


def _parse_vtt(filepath: str) -> list[SubtitleSegment]:
    """Parse a VTT subtitle file into segments."""
    segments = []
    timestamp_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    )

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        for i, line in enumerate(lines):
            match = timestamp_pattern.match(line)
            if match:
                start = _vtt_time_to_seconds(match.group(1))
                end = _vtt_time_to_seconds(match.group(2))
                text = " ".join(lines[i + 1:]).strip()
                # Remove VTT tags
                text = re.sub(r"<[^>]+>", "", text)
                if text:
                    segments.append(SubtitleSegment(
                        start=start, end=end, text=text
                    ))
                break

    return segments


def _vtt_time_to_seconds(time_str: str) -> float:
    """Convert VTT timestamp to seconds."""
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s, ms = parts[2].split(".")
    return h * 3600 + m * 60 + int(s) + int(ms) / 1000.0
