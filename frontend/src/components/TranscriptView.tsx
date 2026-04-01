import { useState, useCallback } from "react";
import { Copy, Download, Check, Search } from "lucide-react";
import { TranscriptionResult, exportTranscript } from "../services/api";

interface TranscriptViewProps {
  result: TranscriptionResult;
  taskId: string;
  onReset: () => void;
}

type ExportFormat = "txt" | "srt" | "vtt" | "markdown";

function formatTimestamp(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h.toString().padStart(2, "0")}:${m
      .toString()
      .padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }
  return `${m.toString().padStart(2, "0")}:${s
    .toString()
    .padStart(2, "0")}`;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function sourceLabel(source: string): string {
  switch (source) {
    case "youtube_subtitle":
      return "YouTube 字幕";
    case "whisper_local":
      return "Whisper 本地转录";
    case "manual_upload":
      return "本地文件转录";
    default:
      return source;
  }
}

export function TranscriptView({
  result,
  taskId,
  onReset,
}: TranscriptViewProps) {
  const [copied, setCopied] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showExportMenu, setShowExportMenu] = useState(false);

  const fullText = result.segments
    .map((s) => `[${formatTimestamp(s.start)}] ${s.text}`)
    .join("\n\n");

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(fullText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [fullText]);

  const handleExport = useCallback(
    async (format: ExportFormat) => {
      setShowExportMenu(false);
      try {
        const res = await exportTranscript(taskId, format);
        // Trigger download
        const blob = new Blob([res.content], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = res.filename;
        a.click();
        URL.revokeObjectURL(url);
      } catch (err: any) {
        console.error("Export failed:", err);
        alert(`导出失败: ${err.message}`);
      }
    },
    [taskId]
  );

  // Filter segments by search query
  const filteredSegments = searchQuery
    ? result.segments.filter((s) =>
        s.text.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : result.segments;

  return (
    <div className="transcript-view">
      {/* Header */}
      <div className="transcript-header">
        <div className="transcript-title-row">
          <h2>{result.title || "转录结果"}</h2>
          <button className="btn-secondary btn-sm" onClick={onReset}>
            新转录
          </button>
        </div>

        <div className="transcript-meta">
          <span>时长: {formatDuration(result.duration)}</span>
          <span>语言: {result.language}</span>
          <span>来源: {sourceLabel(result.source)}</span>
          {result.model && <span>模型: {result.model}</span>}
        </div>
      </div>

      {/* Actions */}
      <div className="transcript-actions">
        <button className="btn-secondary" onClick={handleCopy}>
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? "已复制" : "复制全文"}
        </button>

        <div className="export-dropdown">
          <button
            className="btn-secondary"
            onClick={() => setShowExportMenu(!showExportMenu)}
          >
            <Download size={16} />
            导出
          </button>
          {showExportMenu && (
            <div className="export-menu">
              <button onClick={() => handleExport("txt")}>TXT</button>
              <button onClick={() => handleExport("srt")}>SRT</button>
              <button onClick={() => handleExport("vtt")}>VTT</button>
              <button onClick={() => handleExport("markdown")}>
                Markdown
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="transcript-search">
        <Search size={16} />
        <input
          type="text"
          placeholder="搜索转录内容..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <span className="search-count">
            {filteredSegments.length} / {result.segments.length}
          </span>
        )}
      </div>

      {/* Transcript Content */}
      <div className="transcript-content">
        {filteredSegments.map((seg, i) => (
          <div key={i} className="transcript-segment">
            <span className="segment-time">
              [{formatTimestamp(seg.start)}]
            </span>
            <span className="segment-text">{seg.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
