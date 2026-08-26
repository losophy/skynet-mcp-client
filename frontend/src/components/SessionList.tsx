import type { SessionSummary } from "../types/agent";

interface Props {
  sessions: SessionSummary[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export default function SessionList({ sessions, currentId, onSelect, onNew }: Props) {
  return (
    <aside className="w-64 shrink-0 bg-white border-r border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <span className="font-semibold text-sm">skynet-mcp-client</span>
        <button
          onClick={onNew}
          className="px-2 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700"
          title="新建会话"
        >
          ＋ 新会话
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sessions.length === 0 && (
          <p className="text-xs text-gray-400 px-2 pt-4 text-center">暂无历史会话</p>
        )}
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`w-full text-left px-3 py-2 rounded-md text-sm truncate ${
              currentId === s.id ? "bg-blue-50 text-blue-700" : "hover:bg-gray-100"
            }`}
          >
            {s.title || `会话 ${s.id.slice(0, 8)}`}
            <span className="block text-[10px] text-gray-400 mt-0.5">
              {s.updated_at?.replace("T", " ").slice(0, 16)}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
