# TranscriptPro

> YouTube 长视频转录桌面客户端 — 本地运行，完整逐字稿

## 功能

- 📎 粘贴 YouTube URL，自动转录
- 🎤 Whisper 本地语音识别（离线可用）
- 📝 带时间戳的完整逐字稿
- 💾 多格式导出（SRT / VTT / TXT / Markdown）
- 🌐 AI 翻译（专业版，需 API Key）
- 📁 支持本地视频文件

## 技术栈

- **桌面框架**: Tauri 2.0
- **前端**: React + Vite + TypeScript
- **后端**: Python (FastAPI) — 内嵌运行
- **转录**: faster-whisper (CTranslate2)
- **视频下载**: yt-dlp
- **音频处理**: ffmpeg
- **本地存储**: SQLite

## 项目结构

```
transcriptpro/
├── backend/          # Python 后端（FastAPI + Whisper + yt-dlp）
│   ├── app/          # 应用代码
│   ├── models/       # Whisper 模型存储（.gitignore）
│   └── requirements.txt
├── frontend/         # React + Tauri 前端
│   ├── src/          # React 源码
│   ├── src-tauri/    # Tauri 配置和 Rust glue
│   └── package.json
├── docs/             # PRD 和文档
├── scripts/          # 构建和打包脚本
└── README.md
```

## 开发

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m app.main

# 前端
cd frontend
pnpm install
pnpm tauri dev
```

## License

Proprietary — All rights reserved.
