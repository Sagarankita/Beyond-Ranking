import ReactEChartsCore from "echarts-for-react/lib/core";
import type { EChartsOption } from "echarts";
import { echarts } from "../charts/echarts";
import type { AllocationDatum } from "../data/types";
import { formatValue, titleCase } from "../data/format";

export function AllocationChart({ rows, strategyLabel }: { rows: AllocationDatum[]; strategyLabel: string }) {
  const normalized = rows.map((row) => {
    const maximum = Math.max(Math.abs(row.current), Math.abs(row.recommended), 1);
    return {
      ...row,
      currentPercent: Math.abs(row.current) / maximum * 100,
      recommendedPercent: Math.abs(row.recommended) / maximum * 100,
    };
  });

  const option: EChartsOption = {
    animationDuration: 450,
    grid: { left: 12, right: 30, top: 38, bottom: 12, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { color: "#66716a", fontSize: 11 },
      data: ["Current", strategyLabel],
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (items) => {
        const list = Array.isArray(items) ? items : [items];
        const index = list[0]?.dataIndex ?? 0;
        const row = normalized[index];
        if (!row) return "";
        const difference = row.recommended - row.current;
        return [
          `<strong>${titleCase(row.variable)}</strong>`,
          `Current: ${formatValue(row.current, row.unit)}`,
          `${strategyLabel}: ${formatValue(row.recommended, row.unit)}`,
          `Difference: ${difference >= 0 ? "+" : ""}${formatValue(difference, row.unit)}`,
          `<span style="color:#79827d">Normalized within this decision only.</span>`,
        ].join("<br/>");
      },
    },
    xAxis: { type: "value", max: 100, show: false },
    yAxis: {
      type: "category",
      inverse: true,
      data: normalized.map((row) => titleCase(row.variable)),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#35423a", fontSize: 11, width: 160, overflow: "truncate" },
    },
    series: [
      {
        name: "Current",
        type: "bar",
        barWidth: 8,
        barGap: "60%",
        itemStyle: { color: "#c8cec9", borderRadius: [0, 5, 5, 0] },
        data: normalized.map((row) => row.currentPercent),
      },
      {
        name: strategyLabel,
        type: "bar",
        barWidth: 8,
        itemStyle: { color: "#315b45", borderRadius: [0, 5, 5, 0] },
        data: normalized.map((row) => row.recommendedPercent),
      },
    ],
  };

  return (
    <>
      <ReactEChartsCore echarts={echarts} option={option} style={{ height: Math.max(320, rows.length * 42) }} notMerge />
      <p className="chart-footnote">
        Bars are normalized within each decision so monetary and effort units are never compared on one numeric axis. Hover for exact saved values.
      </p>
    </>
  );
}
