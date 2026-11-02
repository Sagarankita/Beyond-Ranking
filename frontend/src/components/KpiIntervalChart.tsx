import ReactEChartsCore from "echarts-for-react/lib/core";
import type { EChartsOption } from "echarts";
import { echarts } from "../charts/echarts";
import type { KpiDatum } from "../data/types";
import { formatNumber, titleCase } from "../data/format";

export function KpiIntervalChart({ rows }: { rows: KpiDatum[] }) {
  const normalized = rows.map((row) => {
    const maximum = Math.max(row.currentUpper, row.recommendedUpper, row.current, row.recommended, 1) * 1.05;
    return {
      ...row,
      currentPercent: row.current / maximum * 100,
      recommendedPercent: row.recommended / maximum * 100,
      lowerPercent: row.recommendedLower / maximum * 100,
      intervalPercent: (row.recommendedUpper - row.recommendedLower) / maximum * 100,
    };
  });

  const option: EChartsOption = {
    animationDuration: 450,
    grid: { left: 12, right: 26, top: 18, bottom: 18, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (items) => {
        const list = Array.isArray(items) ? items : [items];
        const index = list[0]?.dataIndex ?? 0;
        const row = normalized[index];
        if (!row) return "";
        return [
          `<strong>${titleCase(row.kpi)}</strong>`,
          `Current: ${formatNumber(row.current, 3)} (${formatNumber(row.currentLower, 3)}–${formatNumber(row.currentUpper, 3)})`,
          `Recommended: ${formatNumber(row.recommended, 3)} (${formatNumber(row.recommendedLower, 3)}–${formatNumber(row.recommendedUpper, 3)})`,
          `Evidence: ${titleCase(row.evidence)}`,
          `<span style="color:#79827d">Each KPI uses its own scale.</span>`,
        ].join("<br/>");
      },
    },
    xAxis: { type: "value", max: 100, show: false },
    yAxis: {
      type: "category",
      inverse: true,
      data: normalized.map((row) => titleCase(row.kpi)),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#35423a", fontSize: 11, width: 175, overflow: "truncate" },
    },
    series: [
      {
        name: "Interval offset",
        type: "bar",
        stack: "interval",
        silent: true,
        barWidth: 10,
        itemStyle: { color: "transparent" },
        data: normalized.map((row) => row.lowerPercent),
      },
      {
        name: "Recommended interval",
        type: "bar",
        stack: "interval",
        barWidth: 10,
        itemStyle: { color: "#b8cec0", borderRadius: 6 },
        data: normalized.map((row) => row.intervalPercent),
      },
      {
        name: "Current prediction",
        type: "scatter",
        symbol: "circle",
        symbolSize: 10,
        itemStyle: { color: "#d17a47", borderColor: "#fff", borderWidth: 2 },
        data: normalized.map((row, index) => [row.currentPercent, index]),
      },
      {
        name: "Recommended prediction",
        type: "scatter",
        symbol: "diamond",
        symbolSize: 12,
        itemStyle: { color: "#315b45", borderColor: "#fff", borderWidth: 2 },
        data: normalized.map((row, index) => [row.recommendedPercent, index]),
      },
    ],
  };

  return (
    <>
      <ReactEChartsCore echarts={echarts} option={option} style={{ height: Math.max(250, rows.length * 42) }} notMerge />
      <div className="inline-legend" aria-label="KPI chart legend">
        <span><i className="interval" />Recommended interval</span>
        <span><i className="current" />Current prediction</span>
        <span><i className="recommended" />Recommended prediction</span>
      </div>
      <p className="chart-footnote">Intervals are persisted model outputs, not confidence in a causal effect. Each KPI is normalized only for layout.</p>
    </>
  );
}
