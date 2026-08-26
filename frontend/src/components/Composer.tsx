import { useRef, useState } from "react";

interface Props {
  disabled: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export default function Composer({ disabled, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const t = text.trim();
    if (!t || disabled) return;
    onSend(t);
    setText("");
  };

  return (
    <div className="p-4 border-t border-gray-200 bg-white">
      <div className="flex items-end gap-2 max-w-4xl mx-auto">
        <textarea
          ref={taRef}
          value={text}
          rows={1}
          placeholder={disabled ? "处理中…" : "直接描述你的需求，例如：列出所有服务"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          className="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-4 text-base h-16 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {disabled ? (
          <button
            onClick={onStop}
            className="self-stretch flex items-center justify-center px-6 rounded-lg bg-gray-200 text-gray-700 text-base hover:bg-gray-300"
          >
            停止
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim()}
            className="self-stretch flex items-center justify-center px-6 rounded-lg bg-blue-600 text-white text-base hover:bg-blue-700 disabled:opacity-40"
          >
            发送
          </button>
        )}
      </div>
      <p className="text-xs text-gray-500 text-center mt-2">
        Enter 发送 · Shift+Enter 换行 · 危险命令会先弹出审批确认
      </p>
    </div>
  );
}
