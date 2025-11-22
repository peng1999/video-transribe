import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export type JobStage =
  | "pending"
  | "downloading"
  | "transcribing"
  | "formatting"
  | "done"
  | "error";

export type Provider = "openai" | "bailian";

export interface Job {
  id: string;
  url: string;
  provider: Provider;
  status: JobStage;
  raw_text?: string;
  formatted_text?: string;
  error?: string;
  created_at: string;
  updated_at: string;
}

export async function createJob(url: string, provider: Provider) {
  const res = await api.post<Job>("/jobs", { url, provider });
  return res.data;
}

export async function listJobs() {
  const res = await api.get<{ jobs: Job[] }>("/jobs");
  return res.data.jobs;
}

export async function getJob(id: string) {
  const res = await api.get<Job>(`/jobs/${id}`);
  return res.data;
}

export async function regenerateJob(id: string) {
  const res = await api.post<Job>(`/jobs/${id}/regenerate`);
  return res.data;
}

export function subscribeJob(
  jobId: string,
  onMessage: (data: any) => void,
  onClose?: (event: CloseEvent) => void,
) {
  const ws = new WebSocket(
    `${location.origin.replace("http", "ws")}/api/ws/jobs/${jobId}`,
  );
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error("failed to parse ws message", e);
    }
  };
  ws.onclose = (event) => {
    console.debug("ws onclose", { code: event.code, reason: event.reason });
    onClose?.(event);
  };
  return ws;
}
