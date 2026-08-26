import { Fragment, type ReactNode } from "react";

type Inline =
  | { kind: "text"; value: string }
  | { kind: "bold" | "code"; value: string };

type Block =
  | { kind: "paragraph"; inlines: Inline[] }
  | { kind: "table"; rows: string[][] };

function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) out.push({ kind: "text", value: s.slice(last, m.index) });
    const tok = m[0];
    if (tok.startsWith("**")) out.push({ kind: "bold", value: tok.slice(2, -2) });
    else out.push({ kind: "code", value: tok.slice(1, -1) });
    last = m.index + tok.length;
  }
  if (last < s.length) out.push({ kind: "text", value: s.slice(last) });
  return out;
}

function isSepLine(s: string): boolean {
  const t = s.trim();
  if (!t) return false;
  if (/^\|?[\s:|-]+\|?$/.test(t) && t.includes("-")) return true;
  if (/^\+[-+=]+\+$/.test(t.replace(/\s/g, ""))) return true;
  return false;
}

function splitRow(s: string): string[] {
  let t = s.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) =>
    c.trim().replace(/^\*\*|\*\*$/g, "").replace(/^`|`$/g, "").trim(),
  );
}

export function parseMarkdown(text: string): Block[] {
  const lines = text.split(/\r?\n/);
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (ln.includes("|") && i + 1 < lines.length && isSepLine(lines[i + 1])) {
      const rows: string[][] = [];
      rows.push(splitRow(ln));
      i += 2;
      while (
        i < lines.length &&
        lines[i].includes("|") &&
        !isSepLine(lines[i])
      ) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      blocks.push({ kind: "table", rows });
      continue;
    }
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !(lines[i].includes("|") && i + 1 < lines.length && isSepLine(lines[i + 1]))
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length) {
      blocks.push({
        kind: "paragraph",
        inlines: parseInline(paraLines.join("\n")),
      });
    } else {
      i++;
    }
  }
  return blocks;
}

function renderInline(inlines: Inline[]): ReactNode {
  return inlines.map((t, idx) => {
    if (t.kind === "bold")
      return (
        <strong key={idx} className="font-semibold">
          {t.value}
        </strong>
      );
    if (t.kind === "code")
      return (
        <code
          key={idx}
          className="px-1 py-0.5 bg-gray-100 rounded text-[12px] font-mono"
        >
          {t.value}
        </code>
      );
    return <Fragment key={idx}>{t.value}</Fragment>;
  });
}

export default function MarkdownMessage({ text }: { text: string }) {
  const blocks = parseMarkdown(text);
  return (
    <div className="space-y-2">
      {blocks.map((b, i) =>
        b.kind === "table" ? (
          <div
            key={i}
            className="bg-white border border-gray-200 rounded-lg overflow-hidden"
          >
            <table className="w-full text-xs">
              <tbody>
                {b.rows.map((row, ri) => (
                  <tr
                    key={ri}
                    className={
                      ri === 0
                        ? "bg-gray-50 text-gray-600"
                        : "border-t border-gray-100"
                    }
                  >
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className={`px-3 py-1 ${ri === 0 ? "font-medium" : "font-mono"} whitespace-pre-wrap break-words align-top`}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p key={i} className="text-sm whitespace-pre-wrap leading-relaxed">
            {renderInline(b.inlines)}
          </p>
        ),
      )}
    </div>
  );
}