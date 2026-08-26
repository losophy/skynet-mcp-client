import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { RenderData } from "../types/agent";

interface Props {
  data: RenderData;
  chart: NonNullable<RenderData["chart"]>;
}

/** 基于 render.rows 的 ECharts 封装：bar（横向柱状）/ line（趋势折线） */
export default function ResultChart({ data, chart }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const inst = echarts.init(ref.current);
    chartRef.current = inst;

    const xValues = data.rows.map((r) => String(r[chart.xField] ?? ""));
    const yValues = data.rows.map((r) => Number(r[chart.yField] ?? 0));

    const isBar = chart.type === "bar";
    const option: echarts.EChartsOption = {
      title: chart.title ? { text: chart.title, textStyle: { fontSize: 12 } } : undefined,
      tooltip: { trigger: "axis" },
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      xAxis: isBar
        ? { type: "value" }
        : { type: "category", data: xValues, axisLabel: { fontSize: 10 } },
      yAxis: isBar
        ? { type: "category", data: xValues, axisLabel: { fontSize: 10 } }
        : { type: "value" },
      series: [
        {
          type: chart.type,
          data: isBar ? yValues : yValues,
          itemStyle: { color: "#3b82f6" },
          barWidth: "60%",
        },
      ],
    };
    inst.setOption(option);

    const onResize = () => inst.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      inst.dispose();
      chartRef.current = null;
    };
  }, [data, chart]);

  return <div ref={ref} className="w-full h-56 bg-white border border-gray-200 rounded-lg" />;
}
