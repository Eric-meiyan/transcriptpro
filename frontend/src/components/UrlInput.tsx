import { useState, useCallback, DragEvent } from "react";
import { Youtube, Upload, ArrowRight } from "lucide-react";

interface UrlInputProps {
  onSubmitUrl: (url: string) => void;
  onSubmitFile: (file: File) => void;
  disabled?: boolean;
  language: string;
  onLanguageChange: (lang: string) => void;
  model: string;
  onModelChange: (model: string) => void;
}

const LANGUAGES = [
  { code: "", label: "自动检测" },
  { code: "en", label: "English" },
  { code: "zh", label: "中文" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "pt", label: "Português" },
  { code: "ru", label: "Русский" },
];

const MODELS = [
  { name: "tiny", label: "Tiny — 最快" },
  { name: "base", label: "Base — 快" },
  { name: "small", label: "Small — 推荐" },
  { name: "medium", label: "Medium — 更精准" },
  { name: "large", label: "Large — 最佳" },
];

export function UrlInput({
  onSubmitUrl,
  onSubmitFile,
  disabled,
  language,
  onLanguageChange,
  model,
  onModelChange,
}: UrlInputProps) {
  const [url, setUrl] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const handleSubmit = useCallback(() => {
    const trimmed = url.trim();
    if (!trimmed) return;
    onSubmitUrl(trimmed);
  }, [url, onSubmitUrl]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSubmit();
    },
    [handleSubmit]
  );

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        onSubmitFile(files[0]);
      }
    },
    [onSubmitFile]
  );

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleFileSelect = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "video/*,audio/*,.mp4,.mkv,.avi,.mov,.webm,.mp3,.wav,.m4a";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) onSubmitFile(file);
    };
    input.click();
  }, [onSubmitFile]);

  return (
    <div className="url-input-container">
      {/* URL Input — pill shape matching web site */}
      <div className="url-input-row">
        <div className="url-input-wrapper">
          <Youtube size={20} className="url-icon" />
          <input
            type="text"
            className="url-input"
            placeholder="Paste YouTube URL here..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
          />
        </div>
        <button
          className="btn-primary"
          onClick={handleSubmit}
          disabled={disabled || !url.trim()}
        >
          Get Transcript
          <ArrowRight size={16} />
        </button>
      </div>

      {/* Trust badges */}
      <div className="trust-badges">
        <span>🔒 Local Processing</span>
        <span>⚡ Offline Support</span>
        <span>📝 Multi-format Export</span>
      </div>

      {/* Divider */}
      <div className="divider">
        <span>或</span>
      </div>

      {/* File Drop Zone */}
      <div
        className={`drop-zone ${isDragging ? "dragging" : ""}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleFileSelect}
      >
        <Upload size={24} />
        <span>拖拽本地视频/音频文件到此处，或点击选择</span>
        <span className="drop-hint">
          支持 MP4, MKV, AVI, MOV, WebM, MP3, WAV
        </span>
      </div>

      {/* Options Row */}
      <div className="options-row">
        <div className="option-group">
          <label>语言</label>
          <select
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
            disabled={disabled}
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        <div className="option-group">
          <label>模型</label>
          <select
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            disabled={disabled}
          >
            {MODELS.map((m) => (
              <option key={m.name} value={m.name}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
