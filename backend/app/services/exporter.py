"""Export transcription results to multiple formats."""

from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str


def to_txt(segments: list[Segment], include_timestamps: bool = True) -> str:
    """Export as plain text with optional timestamps."""
    lines = []
    for seg in segments:
        if include_timestamps:
            ts = _format_timestamp(seg.start)
            lines.append(f"[{ts}] {seg.text}")
        else:
            lines.append(seg.text)
    return "\n\n".join(lines)


def to_srt(segments: list[Segment]) -> str:
    """Export as SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg.start)
        end = _format_srt_time(seg.end)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def to_vtt(segments: list[Segment]) -> str:
    """Export as WebVTT subtitle format."""
    lines = ["WEBVTT", ""]
    for seg in segments:
        start = _format_vtt_time(seg.start)
        end = _format_vtt_time(seg.end)
        lines.append(f"{start} --> {end}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def to_markdown(
    segments: list[Segment],
    title: str = "",
    video_url: str = "",
    duration: float = 0,
    language: str = "",
) -> str:
    """Export as Markdown with metadata header."""
    lines = []

    # Header
    if title:
        lines.append(f"# {title}")
        lines.append("")

    # Metadata
    meta = []
    if video_url:
        meta.append(f"- **Source**: {video_url}")
    if duration:
        meta.append(f"- **Duration**: {_format_duration(duration)}")
    if language:
        meta.append(f"- **Language**: {language}")

    if meta:
        lines.extend(meta)
        lines.append("")
        lines.append("---")
        lines.append("")

    # Content
    lines.append("## Transcript")
    lines.append("")

    for seg in segments:
        ts = _format_timestamp(seg.start)
        lines.append(f"**[{ts}]** {seg.text}")
        lines.append("")

    return "\n".join(lines)


# --- Formatting helpers ---


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as VTT timestamp: HH:MM:SS.mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _format_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"
