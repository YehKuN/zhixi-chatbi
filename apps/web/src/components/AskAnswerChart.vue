<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import * as echarts from "echarts";
import type { ECharts } from "echarts";
import { BarChart3, Download, FileSpreadsheet } from "@lucide/vue";
import { downloadArtifact, getArtifactContent } from "@/api/artifacts";
import { listRunArtifacts } from "@/api/runs";
import type { TableData } from "@/api/types";
import { isSafeChartMime } from "@/lib/artifactContent";
import { downloadBlob, downloadCsv, safeFilename, tableToCsv, todayStamp } from "@/lib/dataExport";
import { buildReportChart, chartScore } from "@/lib/reportChart";
import type { ReportChartPayload } from "@/lib/reportChart";

const props = defineProps<{ runId: string }>();
const emit = defineEmits<{ rendered: [] }>();
const host = ref<HTMLElement | null>(null);
const payload = ref<ReportChartPayload | null>(null);
const imageUrl = ref<string | null>(null);
const imageCaption = ref("分析图表");
const sourceTable = ref<TableData | null>(null);
const chartArtifactId = ref<string | null>(null);
const exporting = ref(false);
let chart: ECharts | null = null;
let observer: ResizeObserver | null = null;

function renderChart() {
  if (host.value === null || payload.value === null) return;
  if (chart === null) chart = echarts.init(host.value);
  chart.setOption(payload.value.option, { notMerge: true });
}

async function loadChart() {
  try {
    const artifacts = await listRunArtifacts(props.runId);
    // 查询结果表格既用于「导出数据」，也是没有图表产物时的绘图兜底。
    const tables: TableData[] = [];
    for (const artifact of artifacts.filter((item) => item.type === "table").slice(0, 6)) {
      const content = await getArtifactContent(artifact.id);
      try {
        const parsed = JSON.parse(await content.blob.text()) as TableData;
        if (Array.isArray(parsed.columns) && Array.isArray(parsed.rows)) tables.push(parsed);
      } catch {
        continue;
      }
    }
    const best = tables.filter((table) => chartScore(table) >= 0).pop() ?? null;
    sourceTable.value = best ?? tables[0] ?? null;

    // 优先展示分析 Agent 自己生成的图表产物，其次用查询结果表格兜底绘图。
    const chartArtifact = artifacts.find((item) => item.type === "chart");
    if (chartArtifact !== undefined) {
      const content = await getArtifactContent(chartArtifact.id);
      if (isSafeChartMime(content.contentType)) {
        imageUrl.value = URL.createObjectURL(content.blob);
        imageCaption.value = chartArtifact.title || "分析图表";
        chartArtifactId.value = chartArtifact.id;
        await nextTick();
        emit("rendered");
        return;
      }
    }
    payload.value = best === null ? null : buildReportChart(best);
    if (payload.value === null) return;
    await nextTick();
    renderChart();
    if (typeof ResizeObserver !== "undefined" && host.value !== null) {
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(host.value);
    }
    emit("rendered");
  } catch {
    payload.value = null;
  }
}

onMounted(loadChart);

function exportTable(): void {
  const table = sourceTable.value;
  if (table === null) return;
  downloadCsv(`${safeFilename(imageCaption.value || "分析结果")}-${todayStamp()}.csv`, tableToCsv(table));
}

async function downloadChart(): Promise<void> {
  const artifactId = chartArtifactId.value;
  if (artifactId === null || exporting.value) return;
  exporting.value = true;
  try {
    const response = await downloadArtifact(artifactId);
    downloadBlob(response.blob, response.filename ?? `${safeFilename(imageCaption.value)}-${todayStamp()}.png`);
  } finally {
    exporting.value = false;
  }
}

onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
  chart = null;
  if (imageUrl.value !== null) URL.revokeObjectURL(imageUrl.value);
});
</script>

<template>
  <figure v-if="imageUrl !== null || payload !== null" class="ask-answer-chart">
    <figcaption>
      <BarChart3 :size="13" />
      <span>{{ imageUrl !== null ? imageCaption : payload?.summary }}</span>
      <em v-if="imageUrl !== null">由本次分析生成</em>
      <div class="ask-answer-chart-actions">
        <button v-if="sourceTable !== null" type="button" title="导出当前分析结果数据" @click="exportTable">
          <FileSpreadsheet :size="12" />导出数据
        </button>
        <button v-if="chartArtifactId !== null" type="button" title="下载图表原图" :disabled="exporting" @click="downloadChart">
          <Download :size="12" />下载图表
        </button>
      </div>
    </figcaption>
    <img v-if="imageUrl !== null" :src="imageUrl" class="ask-answer-chart-image" alt="分析图表" @load="emit('rendered')" />
    <div v-else ref="host" class="ask-answer-chart-canvas" />
    <p v-if="payload !== null && imageUrl === null">{{ payload.note }}</p>
  </figure>
</template>

<style scoped>
.ask-answer-chart { margin: 12px 0 2px; overflow: hidden; border: 1px solid rgba(112, 160, 205, .24); border-radius: 12px; background: #fff; }
.ask-answer-chart figcaption { display: flex; align-items: center; gap: 6px; border-bottom: 1px solid rgba(112, 160, 205, .16); padding: 9px 12px; color: #30405c; font-size: 11.5px; font-weight: 600; }
.ask-answer-chart figcaption > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ask-answer-chart figcaption > em { margin-left: auto; color: #8493a9; font-size: 9.5px; font-style: normal; font-weight: 400; }
.ask-answer-chart-actions { display: flex; flex: none; align-items: center; gap: 4px; margin-left: auto; }
.ask-answer-chart figcaption > em + .ask-answer-chart-actions { margin-left: 2px; }
.ask-answer-chart-actions button {
  display: flex;
  align-items: center;
  gap: 3px;
  border: 1px solid rgba(112, 160, 205, .3);
  border-radius: 6px;
  background: rgba(255, 255, 255, .7);
  padding: 2px 7px;
  color: #4a5c78;
  font-size: 10px;
  font-weight: 400;
  cursor: pointer;
  transition: background .2s ease, border-color .2s ease, color .2s ease;
}
.ask-answer-chart-actions button:hover { border-color: rgba(91, 107, 239, .4); background: #fff; color: #3b4dc0; }
.ask-answer-chart-actions button:disabled { opacity: .55; cursor: default; }
.ask-answer-chart-image { display: block; width: 100%; height: auto; background: #fff; }
.ask-answer-chart-canvas { height: 210px; }
.ask-answer-chart p { margin: 0; border-top: 1px solid rgba(112, 160, 205, .12); padding: 7px 12px; color: #7b8aa1; font-size: 9.5px; }
:global(html[data-theme="dark"]) .ask-answer-chart { border-color: rgba(108, 158, 200, .22); background: rgba(12, 25, 42, .55); }
:global(html[data-theme="dark"]) .ask-answer-chart figcaption { border-bottom-color: rgba(108, 158, 200, .16); color: #d6e6f7; }
:global(html[data-theme="dark"]) .ask-answer-chart figcaption > em { color: #8ba0ba; }
:global(html[data-theme="dark"]) .ask-answer-chart-actions button { border-color: rgba(108, 158, 200, .28); background: rgba(255, 255, 255, .06); color: #c3d4e8; }
:global(html[data-theme="dark"]) .ask-answer-chart-actions button:hover { border-color: rgba(130, 146, 255, .45); background: rgba(255, 255, 255, .12); color: #c7cdff; }
:global(html[data-theme="dark"]) .ask-answer-chart-image { background: #0c192a; }
:global(html[data-theme="dark"]) .ask-answer-chart p { border-top-color: rgba(108, 158, 200, .14); color: #8ba0ba; }
</style>
