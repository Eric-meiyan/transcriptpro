import { useState, useCallback, useRef } from "react";
import {
  startTranscription,
  uploadAndTranscribe,
  getTaskStatus,
  TaskStatus,
  TranscriptionResult,
} from "../services/api";

export type TranscriptionState =
  | "idle"
  | "loading"
  | "transcribing"
  | "completed"
  | "failed"
  | "download_failed";

export interface UseTranscriptionReturn {
  state: TranscriptionState;
  progress: number;
  message: string;
  result: TranscriptionResult | null;
  taskId: string | null;
  transcribeUrl: (
    url: string,
    language?: string,
    model?: string
  ) => Promise<void>;
  transcribeFile: (
    file: File,
    language?: string,
    model?: string
  ) => Promise<void>;
  reset: () => void;
}

export function useTranscription(): UseTranscriptionReturn {
  const [state, setState] = useState<TranscriptionState>("idle");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const pollTask = useCallback(
    (id: string) => {
      pollingRef.current = setInterval(async () => {
        try {
          const status: TaskStatus = await getTaskStatus(id);

          setProgress(status.percent);
          setMessage(status.message);

          if (status.status === "completed" && status.result) {
            setState("completed");
            setResult(status.result);
            stopPolling();
          } else if (status.status === "failed") {
            setState("failed");
            stopPolling();
          } else if (status.status === "download_failed") {
            setState("download_failed");
            stopPolling();
          } else {
            setState("transcribing");
          }
        } catch (err) {
          console.error("Poll error:", err);
          // Don't stop polling on transient errors
        }
      }, 1000);
    },
    [stopPolling]
  );

  const transcribeUrl = useCallback(
    async (url: string, language?: string, model?: string) => {
      setState("loading");
      setProgress(0);
      setMessage("创建转录任务...");
      setResult(null);

      try {
        const res = await startTranscription(url, language, model);
        setTaskId(res.task_id);
        setState("transcribing");
        pollTask(res.task_id);
      } catch (err: any) {
        setState("failed");
        setMessage(err.message || "转录失败");
      }
    },
    [pollTask]
  );

  const transcribeFile = useCallback(
    async (file: File, language?: string, model?: string) => {
      setState("loading");
      setProgress(0);
      setMessage("上传文件...");
      setResult(null);

      try {
        const res = await uploadAndTranscribe(file, language, model);
        setTaskId(res.task_id);
        setState("transcribing");
        pollTask(res.task_id);
      } catch (err: any) {
        setState("failed");
        setMessage(err.message || "上传失败");
      }
    },
    [pollTask]
  );

  const reset = useCallback(() => {
    stopPolling();
    setState("idle");
    setProgress(0);
    setMessage("");
    setResult(null);
    setTaskId(null);
  }, [stopPolling]);

  return {
    state,
    progress,
    message,
    result,
    taskId,
    transcribeUrl,
    transcribeFile,
    reset,
  };
}
