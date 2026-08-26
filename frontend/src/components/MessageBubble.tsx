import type { Message } from "../types/agent";
import HumanApprovalCard from "./HumanApprovalCard";
import ResultChart from "./ResultChart";
import ResultTable from "./ResultTable";

interface Props {
  message: Message;
  onFeedback: (decision: "approve" | "reject") => void;
}

export default function MessageBubble({ message, onFeedback }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2 text-sm whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  const pending = message.pending && message.pending.length > 0;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        {message.content && (
          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-2 text-sm whitespace-pre-wrap">
            {message.content}
            {message.streaming && (
              <span className="inline-block w-2 h-4 ml-1 align-middle bg-gray-400 animate-pulse" />
            )}
          </div>
        )}
        {message.error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-xs whitespace-pre-wrap">
            ⚠ {message.error}
          </div>
        )}
        {message.render && !message.render.fallback && message.render.rows.length > 0 && (
          <>
            <ResultTable data={message.render} />
            {message.render.chart && <ResultChart data={message.render} chart={message.render.chart} />}
          </>
        )}
        {message.render && (message.render.fallback || message.render.rows.length === 0) && (
          <pre className="bg-gray-900 text-green-300 rounded-lg px-4 py-3 text-xs overflow-x-auto whitespace-pre-wrap">
            {message.render.raw}
          </pre>
        )}
        {pending && message.pending && (
          <HumanApprovalCard pendingCalls={message.pending} onFeedback={onFeedback} />
        )}
      </div>
    </div>
  );
}
