"""API routes for TranscriptPro backend (Web service mode).

Tasks are stored in Redis (not in-memory).
Transcription runs in Celery workers.
Progress is pushed via SSE.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.audio_downloader import get_video_info
from app.services.exporter import Segment, to_txt, to_srt, to_vtt, to_markdown
from app.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Redis task helpers ---

TASK_PREFIX = "task:"
RESULT_PREFIX = "result:"


def _task_key(task_id: str) -> str:
    return f"{TASK_PREFIX}{task_id}"


def _result_key(task_id: str) -> str:
    return f"{RESULT_PREFIX}{task_id}"


def get_task(task_id: str) -> dict | None:
    """Get task status from Redis."""
    data = redis_client.get(_task_key(task_id))
    if data is None:
        return None
    return json.loads(data)


def set_task(task_id: str, task: dict, ttl: int | None = None):
    """Set task status in Redis."""
    redis_client.set(
        _task_key(task_id),
        json.dumps(task),
        ex=ttl or settings.result_ttl_seconds,
    )


def get_result(task_id: str) -> dict | None:
    """Get transcription result from Redis."""
    data = redis_client.get(_result_key(task_id))
    if data is None:
        return None
    return json.loads(data)


def set_result(task_id: str, result: dict):
    """Store transcription result in Redis (24h TTL)."""
    redis_client.set(
        _result_key(task_id),
        json.dumps(result),
        ex=settings.result_ttl_seconds,
    )


# --- Request/Response models ---


class TranscribeURLRequest(BaseModel):
    url: str
    language: str | None = None


class TranscribeResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    message: str
    percent: float
    result: dict | None = None


class ExportRequest(BaseModel):
    task_id: str
    format: str  # "txt", "srt", "vtt", "markdown"
    include_timestamps: bool = True


class VideoInfoResponse(BaseModel):
    id: str
    title: str
    duration: float
    thumbnail: str | None
    channel: str | None


# --- Routes ---


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@router.post("/video/info")
async def video_info(url: str) -> VideoInfoResponse:
    """Get video metadata without downloading."""
    info = get_video_info(url)
    if not info:
        raise HTTPException(404, "Cannot get video info")
    return VideoInfoResponse(
        id=info.id,
        title=info.title,
        duration=info.duration,
        thumbnail=info.thumbnail,
        channel=info.channel,
    )


@router.post("/transcribe/url")
async def start_transcribe_url(req: TranscribeURLRequest) -> TranscribeResponse:
    """Start transcription from URL (async Celery task)."""
    from app.workers.celery_worker import transcribe_url_task

    task_id = str(uuid.uuid4())[:12]

    # Store initial status in Redis
    set_task(task_id, {
        "status": "pending",
        "message": "Queued...",
        "percent": 0,
    })

    # Submit to Celery
    transcribe_url_task.delay(
        task_id=task_id,
        url=req.url,
        language=req.language,
        model_name=settings.default_model,
    )

    return TranscribeResponse(
        task_id=task_id,
        status="pending",
        message="Transcription task created",
    )


@router.get("/transcribe/status/{task_id}")
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Get transcription task status."""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    result = None
    if task.get("status") == "completed":
        result = get_result(task_id)

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        message=task["message"],
        percent=task["percent"],
        result=result,
    )


@router.get("/transcribe/progress/{task_id}")
async def stream_progress(task_id: str):
    """SSE endpoint for real-time progress updates."""

    async def event_generator():
        last_status = None
        retry_count = 0
        max_retries = 1800  # 30 minutes max (1 check/sec)

        while retry_count < max_retries:
            task = get_task(task_id)
            if task is None:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            # Only send if status changed
            current = json.dumps(task, sort_keys=True)
            if current != last_status:
                last_status = current

                event_data = {
                    "status": task["status"],
                    "message": task["message"],
                    "percent": task["percent"],
                }

                # Include result when completed
                if task["status"] == "completed":
                    result = get_result(task_id)
                    if result:
                        event_data["result"] = result

                yield f"data: {json.dumps(event_data)}\n\n"

                # End stream on terminal states
                if task["status"] in ("completed", "failed", "download_failed"):
                    break

            await asyncio.sleep(1)
            retry_count += 1

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx: disable buffering
        },
    )


@router.post("/export")
async def export_transcript(req: ExportRequest) -> dict:
    """Export transcript in specified format."""
    task = get_task(req.task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    if task.get("status") != "completed":
        raise HTTPException(400, "Task not completed yet")

    result = get_result(req.task_id)
    if result is None:
        raise HTTPException(410, "Result expired")

    segments = [
        Segment(start=s["start"], end=s["end"], text=s["text"])
        for s in result["segments"]
    ]

    title = result.get("title", "transcript")

    if req.format == "txt":
        content = to_txt(segments, include_timestamps=req.include_timestamps)
        filename = f"{title}.txt"
    elif req.format == "srt":
        content = to_srt(segments)
        filename = f"{title}.srt"
    elif req.format == "vtt":
        content = to_vtt(segments)
        filename = f"{title}.vtt"
    elif req.format == "markdown":
        content = to_markdown(
            segments,
            title=title,
            video_url=result.get("url", ""),
            duration=result.get("duration", 0),
            language=result.get("language", ""),
        )
        filename = f"{title}.md"
    else:
        raise HTTPException(400, f"Unsupported format: {req.format}")

    return {"content": content, "filename": filename}


@router.post("/ytdlp/update")
async def ytdlp_update():
    """Manually trigger yt-dlp update."""
    from app.services.audio_downloader import update_ytdlp
    success = update_ytdlp()
    return {"success": success}
