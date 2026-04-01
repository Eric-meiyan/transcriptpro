import { useState } from "react";
import { UrlInput } from "./components/UrlInput";
import { ProgressPanel } from "./components/ProgressPanel";
import { TranscriptView } from "./components/TranscriptView";
import { useTranscription } from "./hooks/useTranscription";
import "./App.css";

function App() {
  const [language, setLanguage] = useState("");
  const [model, setModel] = useState("small");

  const {
    state,
    progress,
    message,
    result,
    taskId,
    transcribeUrl,
    transcribeFile,
    reset,
  } = useTranscription();

  const handleSubmitUrl = (url: string) => {
    transcribeUrl(url, language || undefined, model);
  };

  const handleSubmitFile = (file: File) => {
    transcribeFile(file, language || undefined, model);
  };

  return (
    <div className="app">
      {/* Header — matches web site: red YT + dark Transcript + purple Pro */}
      <header className="app-header">
        <div className="logo">
          <span className="logo-yt">YT</span>
          <span className="logo-text">Transcript</span>
          <span className="logo-pro">Pro</span>
        </div>
        <span className="version">v0.1.0</span>
      </header>

      {/* Main Content */}
      <main className="app-main">
        {state === "idle" && (
          <UrlInput
            onSubmitUrl={handleSubmitUrl}
            onSubmitFile={handleSubmitFile}
            language={language}
            onLanguageChange={setLanguage}
            model={model}
            onModelChange={setModel}
          />
        )}

        {(state === "loading" || state === "transcribing") && (
          <ProgressPanel message={message} percent={progress} />
        )}

        {state === "completed" && result && taskId && (
          <TranscriptView
            result={result}
            taskId={taskId}
            onReset={reset}
          />
        )}

        {state === "failed" && (
          <div className="error-panel">
            <h3>❌ 转录失败</h3>
            <p>{message}</p>
            <button className="btn-primary" onClick={reset}>
              重试
            </button>
          </div>
        )}

        {state === "download_failed" && (
          <div className="error-panel download-failed">
            <h3>⚠️ 自动下载失败</h3>
            <p>{message}</p>
            <p className="hint">
              请手动下载视频/音频文件后拖入应用进行转录
            </p>
            <div className="error-actions">
              <button
                className="btn-primary"
                onClick={() => {
                  reset();
                  // Switch to file upload mode
                }}
              >
                上传本地文件
              </button>
              <button className="btn-secondary" onClick={reset}>
                重试
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <span>本地运行 · 数据不上传 · 离线可用</span>
      </footer>
    </div>
  );
}

export default App;
