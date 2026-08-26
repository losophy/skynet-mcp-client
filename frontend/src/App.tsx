import { useCallback, useEffect, useRef, useState } from "react";
import Composer from "./components/Composer";
import MessageBubble from "./components/MessageBubble";
import SessionList from "./components/SessionList";
import { deleteSession, fetchSession, fetchStatus, listSessions, streamChat, streamHumanFeedback } from "./lib/agentApi";
import type { AgentEvent, Message, SessionSummary } from "./types/agent";

let msgSeq = 0;
const newId = () => `m${++msgSeq}`;

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState<{ connected: boolean; llm_configured: boolean; tool_count: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const updateLast = useCallback((fn: (m: Message) => Message) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last) next[next.length - 1] = fn(last);
      return next;
    });
  }, []);

  const refreshSessions = useCallback(() => {
    listSessions()
      .then((s) => setSessions(s))
      .catch(() => {});
  }, []);

  const handleEvent = useCallback(
    (event: AgentEvent) => {
      switch (event.type) {
        case "session_created":
          sessionIdRef.current = event.session_id;
          setSessionId(event.session_id);
          refreshSessions();
          break;
        case "progress":
          updateLast((m) => ({ ...m, content: m.content + event.content, streaming: true }));
          break;
        case "human_approval":
          updateLast((m) => ({ ...m, pending: event.pending_calls, streaming: false }));
          break;
        case "result":
          updateLast((m) => ({
            ...m,
            content: event.text || m.content,
            render: event.render,
            pending: null,
            streaming: false,
          }));
          break;
        case "error":
          updateLast((m) => ({ ...m, error: event.message, pending: null, streaming: false }));
          setError(event.message);
          break;
      }
    },
    [updateLast, refreshSessions],
  );

  const runStream = useCallback(
    async (task: (opts: { signal?: AbortSignal; sessionId?: string; onEvent: (e: AgentEvent) => void }) => Promise<void>) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      try {
        await task({
          signal: controller.signal,
          sessionId: sessionIdRef.current ?? undefined,
          onEvent: handleEvent,
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        updateLast((m) => ({ ...m, error: msg, streaming: false }));
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [handleEvent, updateLast],
  );

  const handleSend = useCallback(
    async (text: string) => {
      setError(null);
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "user", content: text },
        { id: newId(), role: "assistant", content: "", streaming: true },
      ]);
      await runStream((opts) => streamChat(text, opts));
    },
    [runStream],
  );

  const handleFeedback = useCallback(
    async (decision: "approve" | "reject") => {
      if (!sessionIdRef.current) return;
      updateLast((m) => ({ ...m, pending: null, streaming: true }));
      await runStream((opts) => streamHumanFeedback(sessionIdRef.current!, decision, opts));
    },
    [runStream, updateLast],
  );

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteSession(id);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
      if (sessionIdRef.current === id) {
        sessionIdRef.current = null;
        setSessionId(null);
        setMessages([]);
      }
      refreshSessions();
    },
    [refreshSessions],
  );

  useEffect(() => {
    fetchStatus()
      .then((s) => setStatus(s))
      .catch(() => setStatus(null));
    listSessions()
      .then((s) => setSessions(s))
      .catch(() => {});
  }, []);

  return (
    <div className="flex h-full bg-gray-50 text-gray-900">
      <SessionList
        sessions={sessions}
        currentId={sessionId}
        onSelect={async (id) => {
          setSessionId(id);
          sessionIdRef.current = id;
          setError(null);
          try {
            const s = await fetchSession(id);
            setMessages(
              s.messages.map((m, i) => ({
                id: `h${i}`,
                role: m.role as Message["role"],
                content: m.content,
              })),
            );
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }}
        onDelete={handleDeleteSession}
        onNew={() => {
          setSessionId(null);
          sessionIdRef.current = null;
          setMessages([]);
          setError(null);
        }}
      />
      <main className="flex-1 flex flex-col min-w-0">
        {status && (
          <div className="px-6 py-1.5 text-xs border-b border-gray-200 bg-white/60 flex items-center gap-3">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                status.connected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span>
              {status.connected
                ? `MCP 已连接 · ${status.tool_count} 个工具`
                : "MCP 未连接（请确认 WSL 内 server 已启动）"}
            </span>
            {!status.llm_configured && (
              <span className="text-amber-600">LLM 未配置（.env 需设置 LLM_MODEL_NAME/LLM_API_KEY/LLM_BASE_URL）</span>
            )}
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-24">
              <p className="text-lg font-medium text-gray-500">skynet 调试助手</p>
              <p className="text-sm mt-1">用自然语言直接控制 skynet debug console</p>
              <p className="text-xs mt-4 text-gray-300">例：列出所有服务 · 查看各服务内存 · 杀掉 watchdog</p>
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} onFeedback={handleFeedback} />
          ))}
        </div>
        {error && <div className="px-6 py-2 text-xs text-red-600 bg-red-50 border-t border-red-100">{error}</div>}
        <Composer disabled={streaming} onSend={handleSend} onStop={handleStop} />
      </main>
    </div>
  );
}
