interface ProgressPanelProps {
  message: string;
  percent: number;
}

export function ProgressPanel({ message, percent }: ProgressPanelProps) {
  return (
    <div className="progress-panel">
      <div className="progress-header">
        <span className="progress-message">{message}</span>
        <span className="progress-percent">{Math.round(percent)}%</span>
      </div>

      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>

      <p className="progress-hint">
        💡 转录完全在本地运行，视频数据不会上传到任何服务器
      </p>
    </div>
  );
}
