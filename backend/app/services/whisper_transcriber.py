"""Layer 2 core: Local Whisper transcription with long video chunking."""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    start: float  # seconds
    end: float
    text: str


@dataclass
class TranscriptionResult:
    segments: list[TranscriptSegment]
    language: str
    duration: float
    model_name: str
    source: str = "whisper_local"


# Progress callback type: (current_chunk, total_chunks, percent)
ProgressCallback = Callable[[int, int, float], None]


class WhisperTranscriber:
    """Local Whisper transcription using faster-whisper."""

    def __init__(
        self,
        model_name: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        self.model_name = model_name
        self.model = None
        self.device = device
        self.compute_type = compute_type

    def load_model(self):
        """Load the Whisper model (lazy loading)."""
        if self.model is not None:
            return

        from faster_whisper import WhisperModel

        model_path = settings.models_dir / f"whisper-{self.model_name}"

        # Determine compute type based on device
        device = self.device
        if device == "auto":
            device = self._detect_device()

        compute_type = self.compute_type
        if compute_type == "auto":
            if device == "cpu":
                compute_type = "int8"
            else:
                compute_type = "float16"

        logger.info(
            f"Loading Whisper model: {self.model_name} "
            f"(device={device}, compute={compute_type})"
        )

        self.model = WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(settings.models_dir),
        )

        logger.info("Whisper model loaded")

    def _detect_device(self) -> str:
        """Detect the best available device."""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "cpu"  # faster-whisper uses CTranslate2, MPS not supported
        except ImportError:
            pass
        return "cpu"

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio file with long video chunking support.

        For files > chunk_duration, splits into chunks and transcribes
        each independently, then merges results.
        """
        self.load_model()

        # Get audio duration
        duration = self._get_audio_duration(audio_path)

        if duration <= settings.chunk_duration_sec + 60:
            # Short enough to process in one go
            segments, detected_lang = self._transcribe_single(
                audio_path, language
            )
            if on_progress:
                on_progress(1, 1, 100.0)
        else:
            # Long video: chunk and process
            segments, detected_lang = self._transcribe_chunked(
                audio_path, duration, language, on_progress
            )

        return TranscriptionResult(
            segments=segments,
            language=detected_lang or language or "unknown",
            duration=duration,
            model_name=self.model_name,
        )

    def _transcribe_single(
        self,
        audio_path: Path,
        language: str | None = None,
    ) -> tuple[list[TranscriptSegment], str | None]:
        """Transcribe a single audio file."""
        segments_iter, info = self.model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=1000,
                speech_pad_ms=400,
            ),
        )

        segments = list(segments_iter)

        # If VAD filtered everything out, retry without VAD
        if not segments:
            logger.warning("VAD filtered all audio, retrying without VAD filter")
            segments_iter, info = self.model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                vad_filter=False,
            )
            segments = list(segments_iter)

        result = []
        for seg in segments:
            result.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
            ))

        return result, info.language

    def _transcribe_chunked(
        self,
        audio_path: Path,
        duration: float,
        language: str | None,
        on_progress: ProgressCallback | None,
    ) -> tuple[list[TranscriptSegment], str | None]:
        """
        Split long audio into chunks and transcribe each.

        Strategy:
        1. Split by chunk_duration with overlap
        2. Transcribe each chunk independently
        3. Merge results, de-duplicating overlap regions
        """
        chunk_dur = settings.chunk_duration_sec
        overlap = settings.chunk_overlap_sec
        step = chunk_dur - overlap

        # Calculate chunks
        chunks = []
        start = 0.0
        while start < duration:
            end = min(start + chunk_dur, duration)
            chunks.append((start, end))
            start += step

        total_chunks = len(chunks)
        logger.info(
            f"Long video: {duration:.0f}s → {total_chunks} chunks "
            f"({chunk_dur}s each, {overlap}s overlap)"
        )

        all_segments = []
        detected_lang = None

        with tempfile.TemporaryDirectory(dir=settings.temp_dir) as tmpdir:
            for i, (chunk_start, chunk_end) in enumerate(chunks):
                # Extract chunk audio using ffmpeg
                chunk_path = Path(tmpdir) / f"chunk_{i:03d}.wav"
                self._extract_chunk(
                    audio_path, chunk_path, chunk_start, chunk_end
                )

                # Transcribe chunk
                segments, lang = self._transcribe_single(
                    chunk_path, language or detected_lang
                )
                if not detected_lang and lang:
                    detected_lang = lang

                # Offset timestamps to absolute position
                for seg in segments:
                    seg.start += chunk_start
                    seg.end += chunk_start

                all_segments.extend(segments)

                # Report progress
                if on_progress:
                    pct = (i + 1) / total_chunks * 100
                    on_progress(i + 1, total_chunks, pct)

                # Clean up chunk file immediately
                chunk_path.unlink(missing_ok=True)

        # Merge and de-duplicate overlap regions
        merged = self._merge_overlapping_segments(all_segments, overlap)

        return merged, detected_lang

    def _extract_chunk(
        self,
        input_path: Path,
        output_path: Path,
        start: float,
        end: float,
    ):
        """Extract a time range from audio file using ffmpeg."""
        duration = end - start
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", str(start),
                "-t", str(duration),
                "-i", str(input_path),
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                str(output_path),
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )

    def _merge_overlapping_segments(
        self,
        segments: list[TranscriptSegment],
        overlap_sec: float,
    ) -> list[TranscriptSegment]:
        """
        Merge segments from overlapping chunks.

        In overlap regions, keep segments from the earlier chunk
        (they tend to have better context from what came before).
        """
        if not segments:
            return segments

        # Sort by start time
        segments.sort(key=lambda s: s.start)

        merged = [segments[0]]
        for seg in segments[1:]:
            prev = merged[-1]

            # If this segment starts before the previous one ends,
            # it's from an overlap region — skip if too close
            if seg.start < prev.end - 0.5:
                # Skip duplicate from overlap
                continue

            # If there's a small gap or the text is different, keep it
            merged.append(seg)

        return merged

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio file duration using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0


# Singleton for reuse (model stays loaded)
_transcriber: WhisperTranscriber | None = None


def get_transcriber(model_name: str = "small") -> WhisperTranscriber:
    """Get or create the Whisper transcriber singleton."""
    global _transcriber
    if _transcriber is None or _transcriber.model_name != model_name:
        _transcriber = WhisperTranscriber(model_name=model_name)
    return _transcriber
