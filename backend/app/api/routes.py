"""API routes for TranscriptPro backend."""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.config import settings
from app.services.transcription_pipeline import (
    TaskProgress,
    TaskStatus,
    TranscriptionOutput,
    TranscriptionError,
    DownloadFailedError,
    transcribe_url,
    transcribe_local_file,
)
from app.services.exporter import Segment, to_txt, to_srt, to_vtt, to_markdown
from app.services.audio_downloader import get_video_info, check_ytdlp_update_available, update_ytdlp

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task storage (replaced by SQLite in production)
tasks: dict[str, dict] = {}


# --- Request/Response models ---


class TranscribeURLRequest(BaseModel):
    url: str
    language: str | None = None
    model_name: str = "small"


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
    return {"status": "ok", "version": "0.1.0"}


@router.post("/video/info")
async def video_info(url: str) -> VideoInfoResponse:
    """Get video metadata without downloading."""
    info = get_video_info(url)
    if not info:
        raise HTTPException(404, "无法获取视频信息")
    return VideoInfoResponse(
        id=info.id,
        title=info.title,
        duration=info.duration,
        thumbnail=info.thumbnail,
        channel=info.channel,
    )


@router.post("/transcribe/url")
async def start_transcribe_url(req: TranscribeURLRequest) -> TranscribeResponse:
    """Start transcription from URL (async task)."""
    task_id = str(uuid.uuid4())[:8]

    tasks[task_id] = {
        "status": TaskStatus.PENDING,
        "message": "排队中...",
        "percent": 0,
        "result": None,
    }

    # Run transcription in background
    asyncio.create_task(_run_transcription_url(task_id, req))

    return TranscribeResponse(
        task_id=task_id,
        status="pending",
        message="转录任务已创建",
    )


@router.post("/transcribe/file")
async def start_transcribe_file(
    file: UploadFile = File(...),
    language: str | None = None,
    model_name: str = "small",
) -> TranscribeResponse:
    """Start transcription from uploaded file."""
    task_id = str(uuid.uuid4())[:8]

    # Save uploaded file to temp
    temp_path = settings.temp_dir / f"upload_{task_id}_{file.filename}"
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    tasks[task_id] = {
        "status": TaskStatus.PENDING,
        "message": "排队中...",
        "percent": 0,
        "result": None,
    }

    asyncio.create_task(
        _run_transcription_file(task_id, temp_path, language, model_name)
    )

    return TranscribeResponse(
        task_id=task_id,
        status="pending",
        message="转录任务已创建",
    )


@router.get("/transcribe/status/{task_id}")
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Get transcription task status."""
    if task_id not in tasks:
        raise HTTPException(404, "任务不存在")

    task = tasks[task_id]
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        message=task["message"],
        percent=task["percent"],
        result=task.get("result"),
    )


@router.post("/export")
async def export_transcript(req: ExportRequest) -> dict:
    """Export transcript in specified format."""
    if req.task_id not in tasks:
        raise HTTPException(404, "任务不存在")

    task = tasks[req.task_id]
    if task["status"] != TaskStatus.COMPLETED:
        raise HTTPException(400, "任务尚未完成")

    result = task["result"]
    segments = [
        Segment(start=s["start"], end=s["end"], text=s["text"])
        for s in result["segments"]
    ]

    if req.format == "txt":
        content = to_txt(segments, include_timestamps=req.include_timestamps)
        filename = f"{result.get('title', 'transcript')}.txt"
    elif req.format == "srt":
        content = to_srt(segments)
        filename = f"{result.get('title', 'transcript')}.srt"
    elif req.format == "vtt":
        content = to_vtt(segments)
        filename = f"{result.get('title', 'transcript')}.vtt"
    elif req.format == "markdown":
        content = to_markdown(
            segments,
            title=result.get("title", ""),
            video_url=result.get("url", ""),
            duration=result.get("duration", 0),
            language=result.get("language", ""),
        )
        filename = f"{result.get('title', 'transcript')}.md"
    else:
        raise HTTPException(400, f"不支持的导出格式: {req.format}")

    return {"content": content, "filename": filename}


@router.post("/ytdlp/update")
async def ytdlp_update():
    """Manually trigger yt-dlp update."""
    success = update_ytdlp()
    return {"success": success}


@router.get("/ytdlp/check-update")
async def ytdlp_check():
    """Check if yt-dlp update is available."""
    available = check_ytdlp_update_available()
    return {"update_available": available}


@router.get("/models/list")
async def list_models():
    """List available Whisper models."""
    models = [
        {"name": "tiny", "size": "~75 MB", "quality": "基础", "speed": "最快"},
        {"name": "base", "size": "~140 MB", "quality": "够用", "speed": "快"},
        {"name": "small", "size": "~460 MB", "quality": "好（推荐）", "speed": "较快"},
        {"name": "medium", "size": "~1.5 GB", "quality": "很好", "speed": "中等"},
        {"name": "large", "size": "~3 GB", "quality": "最佳", "speed": "慢"},
    ]

    # Check which models are downloaded
    for m in models:
        model_dir = settings.models_dir / f"whisper-{m['name']}"
        m["downloaded"] = model_dir.exists()

    return {"models": models}


# --- Background task runners ---


async def _run_transcription_url(task_id: str, req: TranscribeURLRequest):
    """Run URL transcription in background."""
    try:
        def on_progress(progress: TaskProgress):
            tasks[task_id].update({
                "status": progress.status,
                "message": progress.message,
                "percent": progress.percent,
            })

        output = await transcribe_url(
            url=req.url,
            language=req.language,
            model_name=req.model_name,
            on_progress=on_progress,
        )

        tasks[task_id].update({
            "status": TaskStatus.COMPLETED,
            "message": "转录完成！",
            "percent": 100,
            "result": _output_to_dict(output, url=req.url),
        })

    except DownloadFailedError as e:
        tasks[task_id].update({
            "status": TaskStatus.DOWNLOAD_FAILED,
            "message": str(e),
            "percent": 0,
        })
    except TranscriptionError as e:
        tasks[task_id].update({
            "status": TaskStatus.FAILED,
            "message": str(e),
            "percent": 0,
        })
    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        tasks[task_id].update({
            "status": TaskStatus.FAILED,
            "message": f"转录失败: {str(e)}",
            "percent": 0,
        })


async def _run_transcription_file(
    task_id: str,
    file_path: Path,
    language: str | None,
    model_name: str,
):
    """Run file transcription in background."""
    try:
        def on_progress(progress: TaskProgress):
            tasks[task_id].update({
                "status": progress.status,
                "message": progress.message,
                "percent": progress.percent,
            })

        output = await transcribe_local_file(
            file_path=file_path,
            language=language,
            model_name=model_name,
            on_progress=on_progress,
        )

        tasks[task_id].update({
            "status": TaskStatus.COMPLETED,
            "message": "转录完成！",
            "percent": 100,
            "result": _output_to_dict(output),
        })

    except TranscriptionError as e:
        tasks[task_id].update({
            "status": TaskStatus.FAILED,
            "message": str(e),
            "percent": 0,
        })
    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        tasks[task_id].update({
            "status": TaskStatus.FAILED,
            "message": f"转录失败: {str(e)}",
            "percent": 0,
        })
    finally:
        # Clean up uploaded file
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass


def _output_to_dict(output: TranscriptionOutput, url: str = "") -> dict:
    """Convert TranscriptionOutput to serializable dict."""
    return {
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
