/** SSE 事件类型（与后端 backend/routes.py 对齐） */

export interface PendingCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  danger: "safe" | "medium" | "high";
}

export type AgentEvent =
  | { type: "session_created"; session_id: string }
  | { type: "progress"; content: string }
  | { type: "tool_call"; tool: string; arguments: Record<string, unknown>; danger: string }
  | { type: "human_approval"; pending_calls: PendingCall[] }
  | { type: "result"; text: string; render?: RenderData }
  | { type: "error"; message: string };

/** 结构化渲染数据（后端 parsers.py 产出；未解析时 fallback=true 只显示原文） */
export interface RenderData {
  columns: string[];
  rows: Record<string, unknown>[];
  raw: string;
  fallback?: boolean;
  /** 图表配置（P6 由后端在特定工具上附加） */
  chart?: {
    type: "bar" | "line";
    xField: string;
    yField: string;
    title?: string;
  };
}

export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  render?: RenderData;
  pending?: PendingCall[] | null;
  error?: string;
  streaming?: boolean;
}
