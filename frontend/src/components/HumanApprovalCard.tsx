import type { PendingCall } from "../types/agent";

interface Props {
  pendingCalls: PendingCall[];
  onFeedback: (decision: "approve" | "reject") => void;
}

const DANGER_LABEL: Record<string, { text: string; cls: string }> = {
  high: { text: "危险", cls: "bg-red-100 text-red-700" },
  medium: { text: "谨慎", cls: "bg-amber-100 text-amber-700" },
};

export default function HumanApprovalCard({ pendingCalls, onFeedback }: Props) {
  return (
    <div className="border border-amber-300 bg-amber-50 rounded-lg p-3 space-y-2">
      <div className="text-sm font-medium text-amber-800">
        ⚠ 危险命令需要人工确认
      </div>
      <div className="space-y-1.5">
        {pendingCalls.map((c) => (
          <div key={c.id} className="flex items-center gap-2 text-xs">
            <span
              className={`px-1.5 py-0.5 rounded ${DANGER_LABEL[c.danger]?.cls ?? "bg-gray-100 text-gray-600"}`}
            >
              {DANGER_LABEL[c.danger]?.text ?? c.danger}
            </span>
            <code className="bg-white border border-gray-200 rounded px-1.5 py-0.5 font-mono">
              {c.name}
            </code>
            <span className="text-gray-600 font-mono truncate">
              {JSON.stringify(c.arguments)}
            </span>
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onFeedback("approve")}
          className="px-3 py-1.5 rounded bg-red-600 text-white text-xs hover:bg-red-700"
        >
          批准执行
        </button>
        <button
          onClick={() => onFeedback("reject")}
          className="px-3 py-1.5 rounded bg-gray-200 text-gray-700 text-xs hover:bg-gray-300"
        >
          拒绝
        </button>
      </div>
    </div>
  );
}
