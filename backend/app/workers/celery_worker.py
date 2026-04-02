"""Celery worker for transcription tasks."""

import json
import logging

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "transcriptpro",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker process
    task_acks_late=True,  # Ack after completion (crash safety)
    task_time_limit=7200,  # 2 hour hard limit
    task_soft_time_limit=6000,  # 100 min soft limit
)


def _update_task(task_id: str, status: str, message: str, percent: float, extra: dict | None = None):
    """Update task status in Redis."""
    import redis as redis_lib
    r = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
    data = {"status": status, "message": message, "percent": percent}
    if extra:
        data.update(extra)
    r.set(
        f"task:{task_id}",
        json.dumps(data),
        ex=settings.result_ttl_seconds,
    )
    r.close()


def _store_result(task_id: str, result: dict):
    """Store transcription result in Redis."""
    import redis as redis_lib
    r = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
    r.set(
        f"result:{task_id}",
        json.dumps(result),
        ex=settings.result_ttl_seconds,
    )
    r.close()


@celery_app.task(name="transcribe_url", bind=True, max_retries=1)
def transcribe_url_task(self, task_id: str, url: str, language: str | None, model_name: str):
    """Transcribe a YouTube URL (runs in Celery worker process)."""
    import asyncio
    from app.services.transcription_pipeline import (
        TaskProgress,
        TaskStatus,
        TranscriptionOutput,
        TranscriptionError,
        DownloadFailedError,
        transcribe_url,
    )

    logger.info(f"[{task_id}] Starting transcription: {url}")

    def on_progress(progress: TaskProgress):
        extra = {}
        if progress.video_duration:
            extra["video_duration"] = progress.video_duration
        _update_task(task_id, progress.status, progress.message, progress.percent, extra or None)

    try:
        _update_task(task_id, "getting_info", "Getting video info...", 5)

        # Run the async pipeline in a sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            output = loop.run_until_complete(
                transcribe_url(
                    url=url,
                    language=language,
                    model_name=model_name,
                    on_progress=on_progress,
                )
            )
        finally:
            loop.close()

        # Store result
        result = {
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in output.segments
            ],
            "title": output.video_info.title if output.video_info else "",
            "video_id": output.video_info.id if output.video_info else "",
            "thumbnail": output.video_info.thumbnail if output.video_info else None,
            "channel": output.video_info.channel if output.video_info else None,
            "language": output.language,
            "duration": output.duration,
            "source": output.source,
            "model": output.model_name,
            "url": url,
        }

        _store_result(task_id, result)
        _update_task(task_id, "completed", "Transcription complete!", 100)

        logger.info(f"[{task_id}] Completed: {len(output.segments)} segments, "
                     f"source={output.source}, duration={output.duration:.0f}s")

    except DownloadFailedError as e:
        logger.warning(f"[{task_id}] Download failed: {e}")
        _update_task(task_id, "download_failed", str(e), 0)

    except TranscriptionError as e:
        logger.error(f"[{task_id}] Transcription error: {e}")
        _update_task(task_id, "failed", str(e), 0)

    except Exception as e:
        logger.exception(f"[{task_id}] Unexpected error")
        _update_task(task_id, "failed", f"Transcription failed: {str(e)}", 0)
