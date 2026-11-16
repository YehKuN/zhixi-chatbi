import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import type { Scalar, TableData } from "@/api/types";

export interface ReportChartPayload {
  option: EChartsOption;
  summary: string;
  note: string;
}

const monthDisplayLabels: Record<string, string> = {
  jan: "1月", feb: "2月", mar: "3月", apr: "4月", may: "5月", jun: "6月",
  jul: "7月", aug: "8月", sep: "9月", oct: "10月", nov: "11月", dec: "12月",
};
const reportColumnLabels: Record<string, string> = {
  month: "月份",
  month_num: "月份序号",
  sessions: "会话数",
  conversion_rate: "转化率",
  conv_rate: "转化率",
  page_value_bucket: "页面价值分桶",
  avg_page_value: "平均页面价值",
  corr: "相关系数",
  diff_pp: "差值（百分点）",
  rel_change: "相对变化",
  better_month: "更高月份",
  traffic_type: "流量类型",
  visitor_type: "访客类型",
  region: "区域",
  browser: "浏览器",
  operating_systems: "操作系统",
  administrative: "行政页面数",
  product_related: "产品页浏览数",
  bounce_rates: "跳出率",
  exit_rates: "退出率",
  special_day: "特殊日期",
};
const shortCodeLabels: Record<string, string> = {
  traffic_type: "类型",
  region: "区域",
  browser: "浏览器",
  operating_systems: "系统",
};
function reportColumnLabel(name: string) {
  return reportColumnLabels[name] ?? name;
}
function reportValueLabel(column: string, value: Scalar, index: number) {
  if (value === null || value === undefined || value === "") return String(index + 1);
  if (column === "month") {
    const key = String(value).slice(0, 3).toLowerCase();
    return monthDisplayLabels[key] ?? String(value);
  }
  const short = shortCodeLabels[column];
  if (short !== undefined && typeof value === "number") return short + " " + value;
  return String(value);
}
function numericColumnIndexes(table: TableData) {
  return table.columns.map((_, index) => index).filter((index) =>
    table.rows.some((row) => typeof row[index] === "number") &&
    table.rows.every((row) => row[index] === null || typeof row[index] === "number"),
  );
}
function isRateColumn(table: TableData, index: number) {
  if (!/rate|ratio|pct|percent|share|conversion|率|占比/i.test(table.columns[index])) return false;
  const values = table.rows.map((row) => Number(row[index])).filter(Number.isFinite);
  return values.length > 0 && Math.max(...values.map((value) => Math.abs(value))) <= 1.5;
}

export function chartScore(table: TableData) {
  if (table.rows.length < 2) return -1;
  const numeric = numericColumnIndexes(table);
  if (numeric.length === 0) return -1;
  const categorical = table.columns.length - numeric.length;
  return Math.min(table.rows.length, 24) * 2 + numeric.length * 3 + (categorical > 0 ? 6 : 0);
}

export function buildReportChart(table: TableData): ReportChartPayload | null {
  if (table.rows.length < 2) return null;
  const numeric = numericColumnIndexes(table);
  const categorical = table.columns.map((_, index) => index).filter((index) => !numeric.includes(index));
  const xIndex = categorical.length > 0 ? categorical[0] : numeric.length >= 2 ? numeric[0] : -1;
  if (xIndex < 0) return null;
  const seriesIndexes = numeric.filter((index) => index !== xIndex);
  if (seriesIndexes.length === 0) return null;
  const rateIndex = seriesIndexes.find((index) => isRateColumn(table, index));
  const valueIndex = seriesIndexes.find((index) => !isRateColumn(table, index));
  if (rateIndex === undefined && valueIndex === undefined) return null;

  const rows = table.rows.slice(0, 24);
  const labels = rows.map((row, index) => reportValueLabel(table.columns[xIndex], row[xIndex], index));
  const valueValues = valueIndex === undefined ? null : rows.map((row) => Number(row[valueIndex]));
  const rateValues = rateIndex === undefined ? null : rows.map((row) => Number(row[rateIndex]) * 100);
  const rateNames = new Set<string>();
  if (rateValues !== null && rateIndex !== undefined) {
    rateNames.add(reportColumnLabel(table.columns[rateIndex]));
  }
  const series: Array<Record<string, unknown>> = [];
  if (valueValues !== null && valueIndex !== undefined) {
    series.push({
      name: reportColumnLabel(table.columns[valueIndex]),
      type: "bar",
      yAxisIndex: 0,
      data: valueValues,
      barWidth: 18,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "#43d7f5" },
          { offset: 1, color: "rgba(45,186,255,.16)" },
        ]),
      },
    });
  }
  if (rateValues !== null && rateIndex !== undefined) {
    series.push({
      name: reportColumnLabel(table.columns[rateIndex]),
      type: "line",
      yAxisIndex: valueValues === null ? 0 : 1,
      data: rateValues,
      smooth: true,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { width: 2.2, color: "#a08cff" },
      itemStyle: { color: "#b6a4ff" },
    });
  }
  const hasRate = rateValues !== null;
  const hasValue = valueValues !== null;
  const rateMax = Math.max(5, Math.ceil(Math.max(0, ...(rateValues ?? [0])) / 5) * 5);
  const yAxis = hasRate && hasValue
    ? [
        { type: "value" as const, min: 0, splitNumber: 3, axisLabel: { color: "#6f829d", fontSize: 8 }, splitLine: { lineStyle: { color: "rgba(104,153,199,.1)", type: "dashed" as const } }, axisLine: { show: false } },
        { type: "value" as const, min: 0, max: rateMax, splitNumber: 3, axisLabel: { color: "#8b7fd8", fontSize: 8, formatter: "{value}%" }, splitLine: { show: false }, axisLine: { show: false } },
      ]
    : [
        hasRate
          ? { type: "value" as const, min: 0, max: rateMax, splitNumber: 3, axisLabel: { color: "#8b7fd8", fontSize: 8, formatter: "{value}%" }, splitLine: { lineStyle: { color: "rgba(104,153,199,.1)", type: "dashed" as const } }, axisLine: { show: false } }
          : { type: "value" as const, min: 0, splitNumber: 3, axisLabel: { color: "#6f829d", fontSize: 8 }, splitLine: { lineStyle: { color: "rgba(104,153,199,.1)", type: "dashed" as const } }, axisLine: { show: false } },
      ];
  const seriesNames = series.map((item) => String(item.name));
  const labelInterval = labels.length > 8 ? Math.ceil(labels.length / 8) - 1 : 0;
  const summary = reportColumnLabel(table.columns[xIndex]) + " · " + seriesNames.join(" × ");
  const note = "来自本次查询结果 · " + table.row_count + " 行 · " +
    table.columns.map(reportColumnLabel).join(" / ");
  const option: EChartsOption = {
    animationDuration: 800,
    grid: { left: 2, right: hasRate && hasValue ? 30 : 8, top: series.length > 1 ? 22 : 10, bottom: 4, containLabel: true },
    legend: series.length > 1
      ? { top: 0, right: 0, itemWidth: 7, itemHeight: 7, textStyle: { color: "#8091ad", fontSize: 8 }, data: seriesNames }
      : { show: false },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(8,19,39,.96)",
      borderColor: "rgba(77,190,255,.25)",
      textStyle: { color: "#e6f4ff", fontSize: 10 },
      formatter: (raw: unknown) => {
        const items = raw as Array<{ axisValueLabel?: string; marker: string; seriesName: string; value: number }>;
        const head = items[0]?.axisValueLabel ?? "";
        const lines = items.map((item) => item.marker + item.seriesName + "：" +
          Number(item.value).toLocaleString("zh-CN", { maximumFractionDigits: 1 }) +
          (rateNames.has(item.seriesName) ? "%" : ""));
        return [head, ...lines].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      name: reportColumnLabel(table.columns[xIndex]),
      nameTextStyle: { color: "#7d90a8", fontSize: 8 },
      data: labels,
      axisLine: { lineStyle: { color: "rgba(120,165,206,.18)" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#7486a1",
        fontSize: 8,
        margin: 7,
        rotate: labels.length > 8 ? 30 : 0,
        interval: labelInterval,
        formatter: (value: string) => value.length > 14 ? value.slice(0, 13) + "…" : value,
      },
    },
    yAxis,
    series,
  } as EChartsOption;
  return { option, summary, note };
}
