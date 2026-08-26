/**
 * 后端接口客户端：SSE 流式解析（照抄 NL2SQL-AI agentApi.ts 模式）
 * 事件：progress / tool_call / human_approval / result / error / session_created
 */
import type { AgentEvent, SessionSummary } from "../types/agent";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

type StreamOptions = {
  signal?: AbortSignal;
  sessionId?: string;
  onEvent: (event: AgentEvent) => void;
};

async function streamFetch(
  url: string,
  init: RequestInit,
  options: StreamOptions,
) {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(init.headers ?? {}),
    },
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // 非 JSON 响应保持默认
    }
    throw new Error(detail);
  }
  if (!response.body) throw new Error("浏览器未返回可读取的流式响应。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\n\n/);
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const event = parseSseChunk(chunk);
      if (event) options.onEvent(event);
    }
  }
  buffer += decoder.decode();
  const tail = parseSseChunk(buffer);
  if (tail) options.onEvent(tail);
}

/** 发送对话消息（SSE 流式返回） */
export async function streamChat(message: string, options: StreamOptions) {
  await streamFetch(
    `${API_BASE_URL}/api/chat`,
    {
      method: "POST",
      body: JSON.stringify({ message, session_id: options.sessionId }),
    },
    options,
  );
}

/** 危险命令审批续流 */
export async function streamHumanFeedback(
  sessionId: string,
  decision: "approve" | "reject",
  options: StreamOptions,
) {
  await streamFetch(
    `${API_BASE_URL}/api/human-feedback`,
    {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, decision }),
    },
    options,
  );
}

export async function fetchStatus() {
  const r = await fetch(`${API_BASE_URL}/api/status`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<{
    connected: boolean;
    server_name: string | null;
    tool_count: number;
    llm_configured: boolean;
    last_error: string | null;
  }>;
}

function parseSseChunk(chunk: string): AgentEvent | null {
  const payload = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""))
    .join("\n")
    .trim();
  if (!payload) return null;
  try {
    return JSON.parse(payload) as AgentEvent;
  } catch {
    return { type: "error", message: `无法解析后端事件：${payload}` };
  }
}

// ------------------------------------------------------------------ 会话历史（P5 接入 SQLite 后使用）

export async function listSessions(): Promise<SessionSummary[]> {
  const r = await fetch(`${API_BASE_URL}/api/sessions`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/** 历史消息（后端 GET /api/sessions/{id}） */
export interface HistoryMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  ts: string;
  meta: Record<string, unknown>;
}

export async function fetchSession(
  sessionId: string,
): Promise<{ id: string; title: string; messages: HistoryMessage[] }> {
  const r = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const r = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 404) throw new Error(`HTTP ${r.status}`);
}
