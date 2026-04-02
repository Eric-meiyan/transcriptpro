# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

TranscriptPro is a desktop application for transcribing video/audio content. It uses a **Tauri 2.0 + React** frontend with a **Python FastAPI** backend running as a local server. The frontend communicates with the backend via HTTP on `localhost:18562`.

## Development Commands

### Backend
```bash
cd backend
pip install -r requirements.txt        # Install Python dependencies
python -m app.main                     # Start FastAPI server on port 18562
```

### Frontend (Tauri + React)
```bash
cd frontend
pnpm install                           # Install Node dependencies
pnpm tauri dev                         # Start Tauri dev mode (Vite on port 1420)
pnpm build                             # Build React for production
```

Both backend and frontend must be running simultaneously for the app to work.

### No test suite is configured yet.

## Architecture

```
Tauri Desktop App (React, port 1420)
    ↓ HTTP requests to localhost:18562/api
FastAPI Backend (Python)
    ↓
Services: Whisper (local STT), yt-dlp (download), FFmpeg (audio processing)
```

### Backend (`backend/app/`)
- **`main.py`** — FastAPI app entry, runs Uvicorn on port 18562
- **`config.py`** — All paths/settings. App data lives at `~/.transcriptpro/` (models, temp, SQLite DB)
- **`api/routes.py`** — All API endpoints (video info, transcribe URL/file, poll status, export, model list)
- **`services/transcription_pipeline.py`** — Core orchestration with 4-layer fallback strategy:
  1. YouTube subtitle extraction (free, instant)
  2. yt-dlp download → local Whisper transcription
  3. User file upload → local Whisper transcription
  4. Groq API cloud transcription (planned)
- **`services/`** — `whisper_transcriber.py`, `audio_downloader.py`, `subtitle_extractor.py`, `exporter.py`

### Frontend (`frontend/src/`)
- **`App.tsx`** — Main UI, three-panel flow (input → progress → result)
- **`components/`** — `UrlInput.tsx` (URL/file input with drag-drop), `ProgressPanel.tsx`, `TranscriptView.tsx`
- **`hooks/useTranscription.ts`** — State machine for transcription workflow, polls `/api/transcribe/status/{task_id}` every 1s
- **`services/api.ts`** — HTTP client targeting `127.0.0.1:18562/api`

### Tauri (`frontend/src-tauri/`)
- Minimal Rust wrapper — Tauri handles windowing/bundling, no custom Rust commands used in production
- Config: `tauri.conf.json` (window 1000×720, app ID `com.transcriptpro.app`)

### Key Design Decisions
- Tasks are stored **in-memory** (Python dict), not yet persisted to SQLite
- Backend transcription runs as **async background tasks** with progress polling
- Frontend uses **no state management library** — a single custom hook manages all state
- Export supports TXT, SRT, VTT, Markdown formats

## External Dependencies
- **FFmpeg** must be installed system-wide
- **yt-dlp** installed via pip
- **faster-whisper** for local speech recognition (models cached at `~/.transcriptpro/models/`)
