/**
 * API client for TranscriptPro backend.
 * Backend runs locally on port 18562.
 */

const API_BASE = "http://127.0.0.1:18562/api";

export interface VideoInfo {
  id: string;
  title: string;
  duration: number;
  thumbnail: string | null;
  channel: string | null;
}

export interface TranscribeResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  message: string;
  percent: number;
  result: TranscriptionResult | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptionResult {
  segments: TranscriptSegment[];
  title: string;
  video_id: string;
  thumbnail: string | null;
  channel: string | null;
  language: string;
  duration: number;
  source: string;
  model: string | null;
  url: string;
}

export interface WhisperModel {
  name: string;
  size: string;
  quality: string;
  speed: string;
  downloaded: boolean;
}

export interface ExportResult {
  content: string;
  filename: string;
}

// --- API calls ---

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }

  return res.json();
}

export async function getVideoInfo(url: string): Promise<VideoInfo> {
  return request<VideoInfo>(`/video/info?url=${encodeURIComponent(url)}`, {
    method: "POST",
  });
}

export async function startTranscription(
  url: string,
  language?: string,
  modelName: string = "small"
): Promise<TranscribeResponse> {
  return request<TranscribeResponse>("/transcribe/url", {
    method: "POST",
    body: JSON.stringify({
      url,
      language: language || null,
      model_name: modelName,
    }),
  });
}

export async function uploadAndTranscribe(
  file: File,
  language?: string,
  modelName: string = "small"
): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (language) formData.append("language", language);
  formData.append("model_name", modelName);

  const res = await fetch(`${API_BASE}/transcribe/file`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload error: ${res.status}`);
  }

  return res.json();
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  return request<TaskStatus>(`/transcribe/status/${taskId}`);
}

export async function exportTranscript(
  taskId: string,
  format: "txt" | "srt" | "vtt" | "markdown",
  includeTimestamps: boolean = true
): Promise<ExportResult> {
  return request<ExportResult>("/export", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId,
      format,
      include_timestamps: includeTimestamps,
    }),
  });
}

export async function listModels(): Promise<WhisperModel[]> {
  const res = await request<{ models: WhisperModel[] }>("/models/list");
  return res.models;
}

export async function checkYtdlpUpdate(): Promise<boolean> {
  const res = await request<{ update_available: boolean }>(
    "/ytdlp/check-update"
  );
  return res.update_available;
}

export async function updateYtdlp(): Promise<boolean> {
  const res = await request<{ success: boolean }>("/ytdlp/update", {
    method: "POST",
  });
  return res.success;
}
