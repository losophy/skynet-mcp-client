import type { RenderData } from "../types/agent";

export default function ResultTable({ data }: { data: RenderData }) {
  const cols = data.columns;
  if (cols.length === 0) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50 text-gray-600">
            {cols.map((c) => (
              <th key={c} className="px-3 py-1.5 text-left font-medium whitespace-nowrap">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.slice(0, 200).map((row, i) => (
            <tr key={i} className="border-t border-gray-100">
              {cols.map((c) => (
                <td key={c} className="px-3 py-1 font-mono whitespace-nowrap">
                  {String(row[c] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.rows.length > 200 && (
        <div className="px-3 py-1 text-[10px] text-gray-400 bg-gray-50">
          仅显示前 200 行，共 {data.rows.length} 行
        </div>
      )}
    </div>
  );
}
