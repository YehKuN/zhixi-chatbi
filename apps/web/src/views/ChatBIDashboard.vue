<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import type { ECharts, EChartsOption } from "echarts";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, BrainCircuit,
  Check, ChevronDown, CircleHelp, Clock3, Database, Download, FileText, Layers,
  LayoutDashboard, Lightbulb, LogOut, MessageSquareText, MoreHorizontal, Plus, RefreshCw,
  Send, Settings2, ShieldCheck, Sparkles, TrendingUp, Upload, Wallet,
} from "@lucide/vue";
import { useRouter } from "vue-router";
import { getArtifactContent } from "@/api/artifacts";
import { buildApiUrl } from "@/api/client";
import { getDatasetOverview } from "@/api/datasources";
import { listRunArtifacts } from "@/api/runs";
import type { DatasetOverview, Run, Scalar, TableData } from "@/api/types";
import { useDatasourceStore } from "@/stores/datasourceStore";
import { useAuthStore } from "@/stores/authStore";
import { useModelStore } from "@/stores/modelStore";
import { useRunStore } from "@/stores/runStore";
import { useSessionStore } from "@/stores/sessionStore";

type Section = "dashboard" | "query" | "reports" | "ledger" | "finance";
type ToastKind = "success" | "info" | "warning";
type InsightKind = "positive" | "warning" | "neutral";

interface InsightCard {
  kind: InsightKind;
  label: string;
  title: string;
  detail: string;
  time: string;
}

interface ReportChartPayload {
  option: EChartsOption;
  summary: string;
  note: string;
}

const router = useRouter();
const auth = useAuthStore();
const datasources = useDatasourceStore();
const models = useModelStore();
const sessions = useSessionStore();
const runs = useRunStore();
const activeSection = ref<Section>("dashboard");
const question = ref("");
const isAnalyzing = ref(false);
const queryInput = ref<HTMLTextAreaElement | null>(null);
const queryDock = ref<HTMLElement | null>(null);
const pageScroll = ref<HTMLElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const toast = ref<{ message: string; kind: ToastKind } | null>(null);
const latestQuestion = ref("这份数据整体表现如何？");
const aiConclusion = ref("正在读取真实数据源聚合结果…");
const analysisSource = ref("正在连接真实数据源");
const lastUpdated = ref(new Date());
const overview = ref<DatasetOverview | null>(null);
const overviewLoading = ref(false);
const overviewError = ref<string | null>(null);
const runInsights = ref<InsightCard[] | null>(null);
const preferredDatasourceId = ref<string | null>(null);
const trendHost = ref<HTMLElement | null>(null);
const channelHost = ref<HTMLElement | null>(null);
const regionHost = ref<HTMLElement | null>(null);
const reportChartHost = ref<HTMLElement | null>(null);
const reportChartPayload = ref<ReportChartPayload | null>(null);
const reportChartLoading = ref(false);
const reportChartNote = ref("完成一次真实分析后，会从查询结果自动生成图表");
const followupQuestion = ref("");
const followupPending = ref(false);
const followupError = ref<string | null>(null);
const followupInput = ref<HTMLTextAreaElement | null>(null);
const profileOpen = ref(false);
const submittedFrom = ref<"dashboard" | "followup">("dashboard");
const pendingFollowupQuestion = ref("");
let trendChart: ECharts | null = null;
let channelChart: ECharts | null = null;
let regionChart: ECharts | null = null;
let reportChart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;
let reportResizeObserver: ResizeObserver | null = null;
let reportChartRunId: string | null = null;
let reportAutoOpened = false;
let toastTimer: number | null = null;
let overviewRequest = 0;
let loadedDatasourceId: string | null = null;

const navItems = [
  { id: "dashboard" as const, label: "经营驾驶舱", icon: LayoutDashboard },
  { id: "query" as const, label: "智能问数", icon: MessageSquareText },
  { id: "reports" as const, label: "洞察报告", icon: FileText },
  { id: "ledger" as const, label: "数据资产台账", icon: Layers },
  { id: "finance" as const, label: "收支管理", icon: Wallet },
];
const chartPalette = ["#43d7f5", "#6889ff", "#9b7aff", "#39cda7", "#f2b566", "#e57e9c", "#7dd3fc", "#c4b5fd"];
const statusLabels: Record<string, string> = {
  uploaded: "已上传",
  inspecting: "检查中",
  schema_ready: "Schema 就绪",
  building_datalink: "建图中",
  ready: "已就绪",
  failed: "检查失败",
  deleting: "删除中",
  deleted: "已删除",
};

const readyDatasources = computed(() => datasources.items.filter((item) =>
  (item.status === "ready" || item.status === "schema_ready") && item.mask_fields_confirmed,
));
const datasourceReady = computed(() => {
  const ready = readyDatasources.value;
  return ready.find((item) => item.id === preferredDatasourceId.value) ?? ready[0] ?? null;
});
const activeModel = computed(() => models.items.find((item) => item.is_active) ?? null);
const liveAgentReady = computed(() => datasourceReady.value !== null && activeModel.value !== null);
const datasourceLabel = computed(() => datasourceReady.value?.name ?? "尚未连接真实数据源");
const datasourceMeta = computed(() => {
  const source = datasourceReady.value;
  if (!source) return "请先在数据资产页接入数据";
  const table = source.schema?.tables[0];
  const rows = table?.row_count ?? 0;
  return source.type.toUpperCase() + " · " + rows.toLocaleString("zh-CN") + " 条记录 · Schema v" + source.schema_revision;
});
const metrics = computed(() => overview.value?.metrics ?? []);
const prompts = computed(() => overview.value?.prompts ?? []);
const distribution = computed(() => overview.value?.distribution ?? null);
const ranking = computed(() => overview.value?.ranking ?? null);
const alertItems = computed(() => overview.value?.alerts ?? []);
const alertCount = computed(() => alertItems.value.length);
const briefingText = computed(() => {
  const run = runs.currentRun;
  if (run?.status === "running") return "正在基于真实数据源执行受控查询，证据链生成中。";
  if (run?.status === "succeeded") {
    if (run.completion_kind === "partial") {
      return "最近一次分析部分完成，已保留可验证结论与查询产物。";
    }
    if (run.completion_kind === "clarification") {
      return "最近一次分析需要补充范围后才能继续。";
    }
    return "最近一次真实数据分析已完成，结论、SQL 审计与查询产物可在分析工作台中回放。";
  }
  if (overviewLoading.value) return "正在聚合当前数据源，请稍候…";
  return overview.value?.briefing ?? overviewError.value ?? "尚未读取到真实数据聚合结果。";
});
const insightItems = computed<InsightCard[]>(() => {
  if (runInsights.value !== null) return runInsights.value;
  const updated = insightTime.value;
  return (overview.value?.insights ?? []).map((item) => ({
    kind: item.kind,
    label: item.label,
    title: item.title,
    detail: item.detail,
    time: updated,
  }));
});
const insightTime = computed(() => formatMonthDay(lastUpdated.value));
const trendLegend = computed(() => (overview.value?.trend?.series ?? []).map((item) => item.name).join(" · ") || "月度趋势");
const trendLegendItems = computed(() =>
  (overview.value?.trend?.series ?? []).map((item) => ({
    name: item.name,
    tone: item.axis === "rate" ? "violet" : "cyan",
  })),
);
const channelLegend = computed(() => (distribution.value?.items ?? []).map((item, index) => ({
  name: item.name,
  value: item.share_pct.toFixed(1) + "%",
  color: ["cyan", "blue", "violet", "green", "amber"][index] ?? "cyan",
})));
const queryPlaceholder = computed(() => {
  const prompt = prompts.value[0];
  return prompt ? "试试问：" + prompt : "试试问：这份数据整体表现如何？";
});
const todayLabel = computed(() => new Intl.DateTimeFormat("zh-CN", {
  year: "numeric", month: "long", day: "numeric", weekday: "long",
}).format(lastUpdated.value));
const dateRangeLabel = computed(() => overview.value?.period_label ?? "等待真实数据");
const activeTitle = computed(() => ({
  dashboard: "经营驾驶舱",
  query: "智能问数",
  reports: "洞察报告",
  ledger: "数据资产台账",
  finance: "收支管理",
}[activeSection.value]));
const greeting = computed(() => {
  const hour = lastUpdated.value.getHours();
  return hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";
});
const reportRows = computed(() => sessions.sessions
  .filter((session) => session.last_message_at !== null)
  .slice(0, 8)
  .map((session) => ({
    id: session.id,
    title: session.title,
    type: datasourceName(session.selected_datasource_id),
    time: session.last_message_at ? formatDateTime(session.last_message_at) : "—",
  })));
const ledgerRows = computed(() => datasources.items
  .filter((item) => item.status !== "deleted" && item.status !== "deleting")
  .map((item) => {
    const tables = item.schema?.tables ?? [];
    const rowCount = tables.reduce((sum, table) => sum + (table.row_count ?? 0), 0);
    const columnCount = tables.reduce((sum, table) => sum + table.columns.length, 0);
    return {
      id: item.id,
      name: item.name,
      type: item.type.toUpperCase() + " · " + columnCount + " 字段",
      status: statusLabels[item.status] ?? item.status,
      rows: rowCount.toLocaleString("zh-CN") + " 条",
      checkedAt: item.last_test_at ? formatDateTime(item.last_test_at) : "—",
      color: item.status === "ready" || item.status === "schema_ready" ? "cyan" : "amber",
    };
  }));
const ledgerStats = computed(() => {
  const assets = datasources.items.filter((item) => item.status !== "deleted" && item.status !== "deleting");
  const rowTotal = assets.reduce((sum, item) => sum + (item.schema?.tables ?? []).reduce((inner, table) => inner + (table.row_count ?? 0), 0), 0);
  const columnTotal = assets.reduce((sum, item) => sum + (item.schema?.tables ?? []).reduce((inner, table) => inner + table.columns.length, 0), 0);
  const activeModels = models.items.filter((item) => item.is_active).length;
  return [
    { label: "已就绪数据源", value: String(readyDatasources.value.length), note: "共 " + assets.length + " 个数据资产", tone: "cyan" },
    { label: "累计记录数", value: rowTotal.toLocaleString("zh-CN"), note: "真实数据记录", tone: "green" },
    { label: "累计字段数", value: String(columnTotal), note: "已固化 Schema", tone: "violet" },
    { label: "已激活模型", value: String(activeModels), note: activeModels > 0 ? "可执行真实分析" : "待激活分析模型", tone: activeModels > 0 ? "green" : "amber" },
  ];
});
const ledgerNote = computed(() => {
  if (ledgerRows.value.length === 0) return "尚未接入数据资产。请在数据资产页上传真实数据源后再查看台账。";
  const confirmed = readyDatasources.value.length;
  return "当前共 " + ledgerRows.value.length + " 个数据资产，其中 " + confirmed + " 个已完成 Schema 检查与遮蔽字段确认，可直接用于智能问数与证据链分析。";
});
const reportRun = computed<Run | null>(() => {
  const live = runs.currentRun;
  if (live?.status === "succeeded" && live.session_id === sessions.currentSession?.id) return live;
  return sessions.runs.find((run) => run.status === "succeeded") ?? null;
});
const followupMessages = computed(() =>
  sessions.messages.filter((message) => message.content_text.trim()).slice(-6),
);
const followupContext = computed(() => sessions.currentSession?.title ?? "尚无分析会话");
const followupReady = computed(() => liveAgentReady.value && sessions.currentSession !== null);

function notify(message: string, kind: ToastKind = "success") {
  toast.value = { message, kind };
  if (toastTimer !== null) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.value = null; }, 2800);
}
function selectSection(section: Section) {
  activeSection.value = section;
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  if (section === "query") {
    void nextTick(() => {
      queryInput.value?.focus({ preventScroll: true });
      const container = pageScroll.value;
      const dock = queryDock.value;
      if (!container || !dock) return;
      const offset = dock.getBoundingClientRect().top - container.getBoundingClientRect().top;
      container.scrollTo({
        top: Math.max(0, container.scrollTop + offset - 16),
        behavior: motion,
      });
    });
  } else if (section === "dashboard") {
    queryInput.value?.blur();
    void nextTick(() => {
      const container = pageScroll.value;
      if (!container) return;
      // 立即回顶：同时取消可能仍在运行的平滑滚动，避免滚轮上滑被动画锁住。
      container.scrollTo({ top: 0, behavior: "auto" });
      container.scrollTop = 0;
    });
  } else {
    queryInput.value?.blur();
    void nextTick(async () => {
      const container = pageScroll.value;
      if (container) {
        container.scrollTo({ top: 0, behavior: "auto" });
        container.scrollTop = 0;
      }
      if (section === "reports") {
        if (!reportAutoOpened && sessions.currentSession === null && reportRows.value.length > 0) {
          reportAutoOpened = true;
          await openReport(reportRows.value[0].id);
        } else {
          await loadReportChart();
        }
      }
    });
  }
}
function setPointerGlow(event: PointerEvent) {
  const root = event.currentTarget;
  if (root instanceof HTMLElement) {
    const rect = root.getBoundingClientRect();
    root.style.setProperty("--pointer-x", (event.clientX - rect.left) + "px");
    root.style.setProperty("--pointer-y", (event.clientY - rect.top) + "px");
  }
  if (!(event.target instanceof Element)) return;
  const surface = event.target.closest<HTMLElement>(".metric-card, .panel, .interactive");
  if (!surface) return;
  const rect = surface.getBoundingClientRect();
  surface.style.setProperty("--pointer-x", (event.clientX - rect.left) + "px");
  surface.style.setProperty("--pointer-y", (event.clientY - rect.top) + "px");
}
function formatTime(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}
function formatMonthDay(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(date);
}
function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}
function formatCount(value: number) {
  return value.toLocaleString("zh-CN");
}
function datasourceName(id: string | null) {
  if (id === null) return "未绑定数据源";
  return datasources.items.find((item) => item.id === id)?.name ?? "数据源已移除";
}
function sparkPath(values: number[]) {
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values.map((value, index) => {
    const x = 2 + (index / (values.length - 1)) * 96;
    const y = 26 - ((value - min) / span) * 24;
    return (index === 0 ? "M" : "L") + x.toFixed(1) + " " + y.toFixed(1);
  }).join(" ");
}
function metricIcon(key: string) {
  if (key === "conversion") return TrendingUp;
  if (key === "months") return Clock3;
  if (key === "numeric") return BarChart3;
  if (key === "quality" || key === "columns") return ShieldCheck;
  return Database;
}
function insightIcon(kind: InsightKind) {
  if (kind === "warning") return AlertTriangle;
  if (kind === "neutral") return ShieldCheck;
  return TrendingUp;
}
function alertIcon(level: "warning" | "info") {
  return level === "warning" ? AlertTriangle : Activity;
}
function makeIdempotencyKey() {
  const id = globalThis.crypto?.randomUUID?.();
  return id ? "chatbi-" + id : "chatbi-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
}
async function loadOverview(force = false) {
  const source = datasourceReady.value;
  if (!source) {
    loadedDatasourceId = null;
    overview.value = null;
    overviewError.value = null;
    aiConclusion.value = "尚未连接可分析的数据源。请先在数据资产页上传真实数据并确认遮蔽字段。";
    analysisSource.value = "未连接数据源";
    latestQuestion.value = "这份数据整体表现如何？";
    await nextTick();
    renderCharts();
    return;
  }
  if (!force && overview.value && loadedDatasourceId === source.id) return;
  loadedDatasourceId = source.id;
  const requestId = ++overviewRequest;
  overviewLoading.value = true;
  overviewError.value = null;
  try {
    const data = await getDatasetOverview(source.id, force);
    if (requestId !== overviewRequest) return;
    overview.value = data;
    lastUpdated.value = new Date();
    if (runs.currentRun?.status !== "succeeded") {
      runInsights.value = null;
      latestQuestion.value = "这份数据整体表现如何？";
      aiConclusion.value = data.briefing;
      analysisSource.value = "真实数据源 · " + data.datasource_name + " · Schema v" + data.schema_revision;
    }
    await nextTick();
    initCharts();
  } catch (error) {
    if (requestId !== overviewRequest) return;
    overview.value = null;
    overviewError.value = error instanceof Error ? error.message : "真实数据聚合失败";
    aiConclusion.value = "读取真实数据聚合失败：" + overviewError.value;
    analysisSource.value = "数据源聚合失败";
    notify(overviewError.value, "warning");
    await nextTick();
    initCharts();
  } finally {
    if (requestId === overviewRequest) overviewLoading.value = false;
  }
}
async function refreshDashboard() {
  lastUpdated.value = new Date();
  await loadOverview(true);
  notify(overview.value ? "真实数据聚合并已刷新" : "真实数据刷新失败", overview.value ? "success" : "warning");
}
function renderCharts() {
  const data = overview.value;
  if (trendHost.value && data?.trend) {
    const hasRate = data.trend.series.some((item) => item.axis === "rate");
    const rates = data.trend.series.filter((item) => item.axis === "rate").flatMap((item) => item.values);
    const rateMax = Math.max(5, Math.ceil(Math.max(0, ...rates) / 5) * 5);
    const chartSeries = data.trend.series.map((item, index) => {
      if (item.kind === "bar") {
        return {
          name: item.name,
          type: "bar" as const,
          yAxisIndex: 0,
          data: item.values,
          barWidth: 16,
          itemStyle: { borderRadius: [4, 4, 0, 0], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "#43d7f5" }, { offset: 1, color: "rgba(45,186,255,.18)" }]) },
          emphasis: { itemStyle: { color: "#8ceaff" } },
        };
      }
      return {
        name: item.name,
        type: "line" as const,
        yAxisIndex: 1,
        data: item.values,
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { width: 2.5, color: index === 0 ? "#53d6ff" : "#a08cff" },
        itemStyle: { color: index === 0 ? "#6ce6ff" : "#b6a4ff", borderColor: "#071a30", borderWidth: 2 },
      };
    });
    const yAxis = [
      { type: "value" as const, name: "条", min: 0, splitNumber: 4, axisLabel: { color: "#6f829d", fontSize: 9 }, splitLine: { lineStyle: { color: "rgba(104,153,199,.1)", type: "dashed" as const } }, axisLine: { show: false } },
      ...(hasRate ? [{ type: "value" as const, name: "%", min: 0, max: rateMax, splitNumber: 4, axisLabel: { color: "#8b7fd8", fontSize: 9, formatter: "{value}%" }, splitLine: { show: false }, axisLine: { show: false } }] : []),
    ];
    trendChart?.setOption({
      animationDuration: 900,
      grid: { left: 5, right: hasRate ? 30 : 12, top: 14, bottom: 26, containLabel: true },
      legend: { show: false },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(8,19,39,.96)",
        borderColor: "rgba(77,190,255,.25)",
        textStyle: { color: "#e6f4ff", fontSize: 11 },
        formatter: (raw: unknown) => {
          const items = raw as Array<{ marker: string; seriesName: string; value: number; seriesIndex: number }>;
          const series = data.trend?.series ?? [];
          return items.map((item) => item.marker + item.seriesName + "：" + Number(item.value).toLocaleString("zh-CN") + (series[item.seriesIndex]?.axis === "rate" ? "%" : " 条")).join("<br/>");
        },
      },
      xAxis: { type: "category", data: data.trend.labels, axisLine: { lineStyle: { color: "rgba(120,165,206,.18)" } }, axisTick: { show: false }, axisLabel: { color: "#7486a1", fontSize: 10, margin: 12 } },
      yAxis,
      series: chartSeries,
    } as EChartsOption, { notMerge: true });
  }
  if (channelHost.value && data?.distribution) {
    channelChart?.setOption({
      animationDuration: 900,
      tooltip: { trigger: "item", backgroundColor: "rgba(8,19,39,.96)", borderColor: "rgba(77,190,255,.25)", textStyle: { color: "#e6f4ff", fontSize: 11 }, formatter: "{b} · {d}%" },
      color: chartPalette,
      series: [{ type: "pie", radius: ["63%", "84%"], center: ["50%", "50%"], label: { show: false }, labelLine: { show: false }, itemStyle: { borderColor: "#0a1730", borderWidth: 3, borderRadius: 5 }, emphasis: { scale: true, scaleSize: 7 }, data: data.distribution.items.map((item) => ({ value: item.count, name: item.name })) }],
      graphic: [
        { type: "text", left: "center", top: "40%", style: { text: formatCount(data.row_count) + " 条", fill: "#e6f6ff", fontSize: 15, fontWeight: 700, fontFamily: "Inter,sans-serif" } },
        { type: "text", left: "center", top: "56%", style: { text: data.distribution.label, fill: "#7f94b2", fontSize: 9, fontFamily: "Inter,sans-serif" } },
      ],
    } as EChartsOption, { notMerge: true });
  }
  if (regionHost.value && data?.ranking) {
    const values = data.ranking.items.map((item) => data.ranking?.metric_label === "转化率" ? (item.conversion_pct ?? 0) : item.share_pct);
    const maxValue = data.ranking.metric_label === "转化率"
      ? Math.max(10, Math.ceil(Math.max(0, ...values) / 10) * 10)
      : 100;
    regionChart?.setOption({
      animationDuration: 800,
      grid: { left: 2, right: 26, top: 7, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "rgba(8,19,39,.96)", borderColor: "rgba(77,190,255,.25)", textStyle: { color: "#e6f4ff", fontSize: 11 }, valueFormatter: (value) => Number(value).toFixed(1) + "%" },
      xAxis: { type: "value", max: maxValue, show: false },
      yAxis: { type: "category", inverse: true, data: data.ranking.items.map((item) => item.name), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: "#9cb0c9", fontSize: 10, margin: 10 } },
      series: [{ type: "bar", data: values, barWidth: 9, showBackground: true, backgroundStyle: { color: "rgba(81,129,184,.09)", borderRadius: 99 }, itemStyle: { borderRadius: 99, color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: "#38bdf8" }, { offset: 1, color: "#8b7bff" }]) }, label: { show: true, position: "right", color: "#92a9c5", fontSize: 9, formatter: "{c}%" } }],
    } as EChartsOption, { notMerge: true });
  }
}
function initCharts() {
  resizeObserver?.disconnect();
  trendChart?.dispose(); channelChart?.dispose(); regionChart?.dispose();
  trendChart = null; channelChart = null; regionChart = null;
  if (trendHost.value) trendChart = echarts.init(trendHost.value);
  if (channelHost.value) channelChart = echarts.init(channelHost.value);
  if (regionHost.value) regionChart = echarts.init(regionHost.value);
  renderCharts();
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => { trendChart?.resize(); channelChart?.resize(); regionChart?.resize(); });
    [trendHost.value, channelHost.value, regionHost.value].forEach((host) => { if (host) resizeObserver?.observe(host); });
  }
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
function chartScore(table: TableData) {
  if (table.rows.length < 2) return -1;
  const numeric = numericColumnIndexes(table);
  if (numeric.length === 0) return -1;
  const categorical = table.columns.length - numeric.length;
  return Math.min(table.rows.length, 24) * 2 + numeric.length * 3 + (categorical > 0 ? 6 : 0);
}
function buildReportChart(table: TableData): ReportChartPayload | null {
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
function initReportChart() {
  reportResizeObserver?.disconnect();
  reportChart?.dispose();
  reportChart = null;
  const payload = reportChartPayload.value;
  if (payload === null || reportChartHost.value === null) return;
  reportChart = echarts.init(reportChartHost.value);
  reportChart.setOption(payload.option, { notMerge: true });
  if (typeof ResizeObserver !== "undefined") {
    reportResizeObserver = new ResizeObserver(() => reportChart?.resize());
    reportResizeObserver.observe(reportChartHost.value);
  }
}
async function loadReportChart() {
  const run = reportRun.value;
  if (run === null) {
    reportChartRunId = null;
    reportChartPayload.value = null;
    reportChartNote.value = "完成一次真实分析后，会从查询结果自动生成图表";
    initReportChart();
    return;
  }
  if (reportChartRunId === run.id && reportChartPayload.value !== null) {
    await nextTick();
    initReportChart();
    return;
  }
  reportChartRunId = run.id;
  reportChartLoading.value = true;
  try {
    const artifacts = await listRunArtifacts(run.id);
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
    const chartable = tables.filter((table) => chartScore(table) >= 0);
    const best = chartable[chartable.length - 1] ?? null;
    const payload = best ? buildReportChart(best) : null;
    reportChartPayload.value = payload;
    reportChartNote.value = payload?.note ?? (best ? "该查询结果暂不适合生成图表" : "本次运行未返回可绘制的表格结果");
    await nextTick();
    initReportChart();
  } catch (error) {
    reportChartPayload.value = null;
    reportChartNote.value = "图表读取失败：" + (error instanceof Error ? error.message : "未知错误");
    reportChartRunId = null;
    initReportChart();
  } finally {
    reportChartLoading.value = false;
  }
}
function setPrompt(prompt: string) {
  question.value = prompt;
  selectSection("query");
}
function applyRunInsights(reply: string, partial = false) {
  const summary = reply.replace(/\s+/g, " ").slice(0, 72);
  runInsights.value = [
    { kind: partial ? "warning" : "positive", label: "分析结论", title: partial ? "本次分析部分完成" : "本次真实数据分析已完成", detail: summary + (reply.length > 72 ? "…" : ""), time: formatTime(new Date()) },
    { kind: "neutral", label: "证据链", title: runs.sqlAudits.length + " 条 SQL 审计 · " + runs.artifacts.length + " 个产物", detail: "查询语句、结果产物与结论引用均已登记，可在分析工作台回放。", time: formatTime(new Date()) },
    { kind: "warning", label: "数据范围", title: runs.currentRun?.datasource_id ? "已绑定真实数据源" : "数据源已记录", detail: "结论仅覆盖本次只读查询命中的记录，查询上限内的结果不代表全量数据。", time: formatTime(new Date()) },
  ];
}
async function submitQuestion() {
  const prompt = question.value.trim();
  if (!prompt || isAnalyzing.value) return;
  const source = datasourceReady.value;
  if (!liveAgentReady.value || source === null) {
    notify("请先在数据资产中连接真实数据源，并在模型设置中激活分析模型", "warning");
    aiConclusion.value = "当前没有可用的真实数据源或分析模型，无法启动分析。";
    analysisSource.value = "未连接分析引擎";
    return;
  }
  question.value = "";
  latestQuestion.value = prompt;
  isAnalyzing.value = true;
  runInsights.value = null;
  aiConclusion.value = "正在理解业务意图、匹配指标口径并生成查询计划…";
  analysisSource.value = "AI Agent 正在分析真实数据源";
  submittedFrom.value = "dashboard";
  // 提交后保持当前问数位置，不切回驾驶舱顶部。
  try {
    if (!sessions.currentSession || sessions.currentSession.selected_datasource_id !== source.id) {
      await sessions.create("新分析", source.id);
    }
    const runId = await sessions.submitRun(prompt, makeIdempotencyKey());
    await runs.begin(runId);
    notify("分析任务已提交，正在生成证据链", "info");
  } catch (error) {
    isAnalyzing.value = false;
    const message = error instanceof Error ? error.message : "分析任务提交失败";
    aiConclusion.value = "分析任务提交失败：" + message;
    analysisSource.value = "运行未启动";
    notify(message, "warning");
  }
}
function downloadReport() {
  const report = "# 智析 ChatBI · 经营洞察报告\n\n生成时间：" + new Date().toLocaleString("zh-CN") +
    "\n\n## 分析问题\n" + latestQuestion.value + "\n\n## 核心结论\n" + aiConclusion.value +
    "\n\n## 数据说明\n" + analysisSource.value + "\n\n> 请结合企业数据口径和证据材料复核本报告。";
  const url = URL.createObjectURL(new Blob([report], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "智析经营洞察-" + new Date().toISOString().slice(0, 10) + ".md";
  link.click();
  URL.revokeObjectURL(url);
  notify("洞察报告已导出为 Markdown");
}
async function openReport(sessionId: string) {
  await sessions.select(sessionId);
  const reply = [...sessions.messages].reverse().find((item) => item.role === "assistant");
  latestQuestion.value = sessions.currentSession?.title ?? "历史分析会话";
  const historyRun = sessions.runs.find((run) => run.status === "succeeded");
  if (reply?.content_text) {
    aiConclusion.value = reply.content_text;
    applyRunInsights(reply.content_text, historyRun?.completion_kind === "partial");
  }
  analysisSource.value = "历史分析会话 · 可回放 SQL 与证据链";
  followupError.value = null;
  reportChartRunId = null;
  await loadReportChart();
  notify("已载入历史分析会话");
}
async function askFollowUp() {
  const prompt = followupQuestion.value.trim();
  if (!prompt || followupPending.value) return;
  if (!liveAgentReady.value || sessions.currentSession === null) {
    notify("请先在智能问数中完成一次分析，再基于当前报告追问", "warning");
    return;
  }
  followupError.value = null;
  followupPending.value = true;
  pendingFollowupQuestion.value = prompt;
  followupQuestion.value = "";
  submittedFrom.value = "followup";
  try {
    const runId = await sessions.submitRun(prompt, makeIdempotencyKey());
    await runs.begin(runId);
    notify("追问已提交，正在沿用当前会话上下文", "info");
  } catch (error) {
    followupPending.value = false;
    const message = error instanceof Error ? error.message : "追问提交失败";
    followupError.value = message;
    submittedFrom.value = "dashboard";
    notify(message, "warning");
  }
}
function showAlerts() {
  if (alertItems.value.length === 0) {
    notify("当前数据源未触发预警规则", "info");
    return;
  }
  notify(alertItems.value.map((item) => item.title).join("；"), "warning");
}
function openDatasources() { void router.push("/datasources"); }
function openModelSettings() { void router.push("/settings/model"); }
async function handleLogout() {
  profileOpen.value = false;
  await auth.logout();
  await router.push("/login");
}
function openUpload() { fileInput.value?.click(); }
async function handleFileSelected(event: Event) {
  const target = event.currentTarget;
  if (!(target instanceof HTMLInputElement) || !target.files?.length) return;
  const file = target.files[0];
  notify("已选择 " + file.name + "，请在数据资产页完成接入", "info");
  target.value = "";
  await router.push("/datasources");
}

watch(activeSection, async (section) => {
  if (section === "dashboard" || section === "query") {
    await nextTick();
    initCharts();
  }
});
watch(() => runs.currentRun?.status, async (status) => {
  if (status !== "succeeded" && status !== "failed" && status !== "canceled") return;
  isAnalyzing.value = false;
  followupPending.value = false;
  pendingFollowupQuestion.value = "";
  const wasFollowup = submittedFrom.value === "followup";
  submittedFrom.value = "dashboard";
  if (status === "succeeded") {
    const completion = runs.currentRun?.completion_kind;
    if (completion === "partial") {
      analysisSource.value = "分析部分完成 · 已保留可验证结果";
    } else if (completion === "clarification") {
      analysisSource.value = "分析暂停 · 需要补充分析范围";
    } else {
      analysisSource.value = "受控分析引擎 · 已完成真实查询并登记产物";
    }
    const sessionId = sessions.currentSession?.id;
    if (sessionId) {
      await sessions.select(sessionId);
      const reply = [...sessions.messages].reverse().find((item) => item.role === "assistant");
      if (reply?.content_text) {
        aiConclusion.value = reply.content_text;
        applyRunInsights(reply.content_text, completion === "partial");
      }
    }
    reportChartRunId = null;
    if (activeSection.value === "reports") await loadReportChart();
    if (completion === "partial") {
      notify("分析部分完成，可验证结论与查询产物已保留", "warning");
    } else if (completion === "clarification") {
      notify("分析需要补充范围后才能继续", "warning");
    } else {
      notify("分析完成，结论与证据已更新");
    }
  } else {
    const message = runs.currentRun?.error_message ?? "本次分析未能完整完成，请检查数据源配置或查看运行详情。";
    if (wasFollowup) {
      followupError.value = message;
      const sessionId = sessions.currentSession?.id;
      if (sessionId) await sessions.select(sessionId);
      notify("追问未能完成，请查看错误信息", "warning");
      return;
    }
    aiConclusion.value = message;
    analysisSource.value = "运行状态 · 请检查执行记录";
    notify("分析结束，请检查运行状态", "warning");
  }
});
onMounted(async () => {
  await Promise.allSettled([datasources.load(), models.load(), sessions.load()]);
  await loadOverview();
  preferredDatasourceId.value = datasourceReady.value?.id ?? null;
});
watch(preferredDatasourceId, async () => {
  runInsights.value = null;
  await loadOverview();
});
onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  reportResizeObserver?.disconnect();
  trendChart?.dispose(); channelChart?.dispose(); regionChart?.dispose();
  reportChart?.dispose();
  if (toastTimer !== null) window.clearTimeout(toastTimer);
});
</script>

<template>
  <section class="chatbi-app" @pointermove.passive="setPointerGlow">
    <div class="ambient-glow ambient-a" aria-hidden="true" /><div class="ambient-glow ambient-b" aria-hidden="true" />
    <aside class="sidebar">
      <div class="brand-row"><img class="brand-mark chatbi-brand-logo" src="/chatbi-mark.svg" alt="智析 ChatBI 标识" /><div class="brand-name"><strong>智析 <span>ChatBI</span></strong><small>AI 企业数据分析平台</small></div><i class="brand-online" /></div>
      <button type="button" class="workspace-select interactive" @click="openDatasources"><span class="workspace-mark"><Database :size="16" /></span><span class="workspace-copy"><small>当前工作空间</small><strong>{{ datasourceLabel }}</strong></span><ChevronDown :size="14" class="dim" /></button>
      <div class="side-label">分析空间</div>
      <nav class="side-nav" aria-label="工作空间导航">
        <button v-for="item in navItems" :key="item.id" type="button" class="nav-item interactive" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="17" /><span>{{ item.label }}</span><span v-if="item.id === 'reports' && reportRows.length" class="nav-count">{{ reportRows.length }}</span><i v-if="activeSection === item.id" class="nav-active" /></button>
      </nav>
      <div class="side-divider" />
      <div class="side-label side-label-actions"><span>数据资源</span><button type="button" class="tiny-icon interactive" title="导入数据" @click="openUpload"><Plus :size="14" /></button></div>
      <button type="button" class="source-link interactive" @click="openDatasources"><i class="source-dot" /><span class="source-copy"><strong>{{ datasourceLabel }}</strong><small>{{ datasourceMeta }}</small></span><MoreHorizontal :size="15" class="dim" /></button>
      <div class="side-bottom"><div class="engine-card"><div class="engine-heading"><span class="engine-icon"><Sparkles :size="13" /></span><strong>AI 分析引擎</strong><em>{{ liveAgentReady ? "LIVE" : "待配置" }}</em></div><p>{{ liveAgentReady ? activeModel?.model_name + " · 已激活" : "连接真实数据并激活模型" }}</p><div class="engine-meter"><i /></div><small>{{ liveAgentReady ? "Agent · SQL 网关 · DataLink" : "尚未具备真实分析条件" }}</small></div><div class="profile-wrap"><div v-if="profileOpen" class="profile-backdrop" @click="profileOpen = false" /><div v-if="profileOpen" class="profile-popover"><div class="profile-popover-head"><span class="avatar">{{ auth.avatarText }}</span><span class="profile-popover-name"><strong>{{ auth.user?.display_name ?? "未登录" }}</strong><small>{{ auth.roleLabel }} · {{ auth.user?.username ?? "-" }}</small></span></div><div class="profile-row"><span>所属企业</span><strong>{{ auth.enterprise?.name ?? "未绑定企业" }}</strong></div><div class="profile-row"><span>企业 ID</span><strong class="profile-code">{{ auth.enterprise?.code ?? "-" }}</strong></div><button type="button" class="profile-menu-link interactive" @click="openModelSettings"><Settings2 :size="14" />模型与引擎设置</button><button type="button" class="profile-logout-button interactive" @click="handleLogout"><LogOut :size="14" />退出登录</button></div><button type="button" class="profile-link interactive" :class="{ active: profileOpen }" @click="profileOpen = !profileOpen"><span class="avatar">{{ auth.avatarText }}</span><span><strong>{{ auth.user?.display_name ?? "未登录" }}</strong><small>{{ auth.enterprise?.name ?? "未绑定企业" }}</small></span><MoreHorizontal :size="16" /></button></div></div>
    </aside>

    <main class="main-area">
      <header class="topbar"><div class="crumb"><span>工作空间</span><i>/</i><strong>{{ activeTitle }}</strong><span class="realtime"><i />真实数据</span></div><div class="top-actions"><div class="time-label"><i />{{ formatTime(lastUpdated) }} <span>·</span> {{ todayLabel }}</div><button class="icon-action interactive" type="button" title="帮助中心" @click="notify('帮助中心即将开放，欢迎继续探索工作台', 'info')"><CircleHelp :size="17" /></button><button class="icon-action interactive" type="button" title="刷新数据" @click="refreshDashboard"><RefreshCw :size="16" /></button><button class="icon-action interactive notification-icon" type="button" :title="alertCount + ' 条数据提醒'" @click="showAlerts"><i v-if="alertCount" /> <Activity :size="17" /></button><button type="button" class="primary-action interactive" @click="openUpload"><Upload :size="14" />导入数据</button></div></header>
      <div ref="pageScroll" class="page-scroll"><div class="page-content">
        <template v-if="activeSection === 'dashboard' || activeSection === 'query'">
          <section class="page-heading"><div><div class="eyebrow"><i />{{ todayLabel }} · 真实数据总览</div><h1>{{ greeting }}，让数据 <span>回答问题。</span></h1><p>用自然语言探索业务，让每一份洞察都有据可查。</p></div><button type="button" class="date-range interactive" @click="notify(overview ? '当前视图基于「' + overview.datasource_name + '」实时聚合，共 ' + formatCount(overview.row_count) + ' 条真实记录' : '尚未读取到真实数据源', 'info')"><Clock3 :size="15" />{{ dateRangeLabel }}<ChevronDown :size="13" /></button></section>
          <section v-if="metrics.length" class="metric-grid" aria-label="核心数据指标">
            <article v-for="(metric, index) in metrics" :key="metric.key" class="metric-card interactive" :class="'metric-' + metric.tone" :style="{ '--card-index': index }"><div class="metric-top"><span>{{ metric.label }}</span><i><component :is="metricIcon(metric.key)" :size="16" /></i></div><div class="metric-value-row"><strong>{{ metric.value }}</strong><svg v-if="metric.spark.length > 1" class="mini-spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><path :d="sparkPath(metric.spark)" /></svg></div><div class="metric-foot"><span v-if="metric.change" class="metric-change" :class="metric.change_tone"><ArrowUpRight v-if="metric.change_tone !== 'down'" :size="13" /><ArrowDownRight v-else :size="13" />{{ metric.change }}</span><span>{{ metric.detail }}</span></div><i class="metric-accent" /></article>
          </section>
          <section v-else class="panel data-empty overview-empty"><Database :size="22" /><strong>{{ overviewLoading ? "正在聚合真实数据源…" : "尚未连接可分析的数据源" }}</strong><span>{{ overviewError ?? "上传真实数据并确认遮蔽字段后，这里会自动生成指标、趋势与分组洞察。" }}</span><button type="button" class="outline-action interactive" @click="openDatasources">前往数据资产</button></section>
          <section class="main-grid">
            <article class="panel trend-panel"><header class="panel-heading"><div><div class="panel-kicker"><i />数据趋势</div><h2>{{ overview?.trend?.title ?? "月度趋势" }} <span>·</span> <small>Monthly Trend</small></h2></div><div class="panel-tools"><span class="live-pill"><i />真实数据</span><button type="button" class="menu-button interactive" aria-label="趋势选项" @click="notify(overview?.trend?.subtitle ?? '当前数据源暂无月份字段', 'info')"><MoreHorizontal :size="18" /></button></div></header><div class="trend-total"><strong>{{ overview ? formatCount(overview.row_count) : "—" }}</strong><span>条记录</span><em>{{ dateRangeLabel }}</em><div v-if="trendLegendItems.length" class="trend-legend-inline"><span v-for="item in trendLegendItems" :key="item.name"><i class="legend-dot" :class="item.tone" />{{ item.name }}</span></div></div><div v-if="overview?.trend" ref="trendHost" class="trend-chart" role="img" :aria-label="overview.trend.title" /><div v-else class="trend-chart data-empty chart-empty"><span>当前数据源暂无可用的月份字段</span></div><div class="chart-foot"><span><i class="legend-dot cyan" />{{ overview?.trend?.subtitle || trendLegend }}</span><span>更新于 {{ formatTime(lastUpdated) }}</span><button type="button" @click="selectSection('reports')">查看分析 <ArrowUpRight :size="13" /></button></div></article>
            <article class="panel insight-panel"><header class="panel-heading"><div><div class="panel-kicker"><Sparkles :size="13" />数据洞察</div><h2>值得关注的信号</h2></div><button type="button" class="text-action interactive" @click="selectSection('reports')">全部洞察 <ArrowUpRight :size="13" /></button></header><div class="insight-scroll"><div class="briefing"><span class="briefing-orb"><BrainCircuit :size="19" /></span><div><small>REAL DATA BRIEFING</small><p>{{ briefingText }}</p></div></div><div class="insight-list"><button v-for="item in insightItems" :key="item.title" type="button" class="insight-row interactive" :class="'insight-' + item.kind" @click="notify(item.detail, item.kind === 'warning' ? 'warning' : 'info')"><i class="insight-symbol"><component :is="insightIcon(item.kind)" :size="15" /></i><span class="insight-body"><span class="insight-row-meta"><em>{{ item.label }}</em><small>{{ item.time }}</small></span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span><ArrowUpRight :size="14" class="insight-arrow" /></button></div></div><button type="button" class="weekly-link interactive" @click="selectSection('reports')"><span><Lightbulb :size="14" />{{ overview ? "全部指标由真实数据源即时聚合" : "等待真实数据源接入" }}</span><ArrowUpRight :size="14" /></button></article>
          </section>
          <section ref="queryDock" class="query-dock" :class="{ analyzing: isAnalyzing }"><div class="query-head"><div class="query-title"><span><Sparkles :size="14" /></span><strong>问问你的数据</strong><em>AI POWERED</em></div><select v-if="readyDatasources.length > 1" v-model="preferredDatasourceId" class="query-source query-source-select" aria-label="选择分析数据源"><option v-for="item in readyDatasources" :key="item.id" :value="item.id">{{ item.name }}</option></select><button v-else type="button" class="query-source interactive" @click="openDatasources"><Database :size="13" />{{ datasourceLabel }}<ChevronDown :size="13" /></button></div><div class="query-input-row"><textarea ref="queryInput" v-model="question" rows="1" aria-label="输入数据分析问题" :placeholder="queryPlaceholder" @keydown.enter.exact.prevent="submitQuestion" /><div class="query-tools"><button type="button" class="add-question interactive" title="上传数据" @click="openUpload"><Plus :size="17" /></button><i /><button type="button" class="send-button interactive" :disabled="!question.trim() || isAnalyzing" :aria-label="isAnalyzing ? '正在分析' : '发送问题'" @click="submitQuestion"><span v-if="isAnalyzing" class="spinner" /><Send v-else :size="15" /></button></div></div><div class="query-foot"><div class="prompt-list"><span>试试</span><button v-for="prompt in prompts" :key="prompt" type="button" class="prompt-chip interactive" @click="setPrompt(prompt)">{{ prompt }}</button></div><span class="secure-note"><ShieldCheck :size="12" />只读分析 · 数据安全</span></div></section>
          <section class="answer-card"><span class="answer-glyph"><Sparkles :size="16" /></span><div class="answer-body"><div><em>{{ isAnalyzing ? "ANALYZING" : "DATA INSIGHT" }}</em><span><i />{{ analysisSource }}</span></div><p><strong>{{ latestQuestion }}</strong>{{ aiConclusion }}</p></div><button type="button" class="evidence-button interactive" @click="selectSection('reports')"><ShieldCheck :size="14" />查看证据 <span>↗</span></button></section>
          <section class="bottom-grid">
            <article class="panel channel-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">分组结构</div><h2>{{ distribution?.title ?? "字段分布" }}</h2></div><button type="button" class="menu-button interactive" @click="selectSection('reports')"><MoreHorizontal :size="18" /></button></header><div v-if="distribution" class="channel-content"><div ref="channelHost" class="channel-chart" role="img" :aria-label="distribution.title + '环图'" /><div class="channel-legend"><button v-for="item in channelLegend" :key="item.name" type="button" class="interactive" @click="notify(item.name + '占全部记录 ' + item.value, 'info')"><i :class="item.color" />{{ item.name }}<strong>{{ item.value }}</strong></button></div></div><div v-else class="data-empty channel-empty"><span>当前数据源暂无可分组字段</span></div></article>
            <article class="panel region-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">分组表现</div><h2>{{ ranking?.title ?? "分组排名" }}</h2></div><button type="button" class="range-mini interactive" @click="notify('已按' + (ranking?.metric_label ?? '占比') + '由高到低排序', 'info')">全量 <ChevronDown :size="12" /></button></header><div v-if="ranking" ref="regionHost" class="region-chart" role="img" :aria-label="ranking.title + '横向柱状图'" /><div v-else class="region-chart data-empty chart-empty"><span>当前数据源暂无可排名分组</span></div><div v-if="ranking" class="region-foot"><span><i class="legend-dot cyan" />{{ ranking.label }} · {{ ranking.metric_label }}</span><strong>{{ ranking.items[0]?.name }} {{ ranking.items[0]?.conversion_pct ?? ranking.items[0]?.share_pct }}%</strong><button type="button" @click="notify('排名由当前数据源实时聚合', 'info')">数据口径 <CircleHelp :size="12" /></button></div></article>
            <article class="panel alert-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">数据监测</div><h2>数据预警 <em v-if="alertCount" class="alert-count">{{ alertCount }}</em></h2></div><button type="button" class="text-action interactive" @click="showAlerts">查看全部 <ArrowUpRight :size="13" /></button></header><button v-for="(alert, index) in alertItems" :key="alert.title" type="button" class="alert-row interactive" :class="{ 'amber-alert': alert.level === 'info' || index > 0 }" @click="notify(alert.detail, alert.level)"><i><component :is="alertIcon(alert.level)" :size="14" /></i><span><strong>{{ alert.title }}</strong><small>{{ alert.detail }}</small></span><em>{{ alert.level === "warning" ? "关注" : "分析" }}</em></button><div v-if="alertItems.length === 0" class="alert-empty"><span>当前数据源未触发预警规则</span></div><div class="alert-foot"><span><i />聚合规则运行正常</span><small>{{ formatTime(lastUpdated) }} 更新</small></div></article>
          </section>
          <footer class="page-footer"><span>智析 ChatBI <i>·</i> 让每个决策都有数据依据</span><span>Agent <i class="footer-agent" />{{ liveAgentReady ? "已连接" : "待配置" }} <b>·</b> {{ runs.currentRun?.status === "running" ? "分析执行中" : runs.currentRun?.status === "succeeded" ? "刚刚完成一次分析" : overview ? "真实数据已同步" : "等待数据源" }}</span></footer>
        </template>

        <template v-else-if="activeSection === 'reports'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />REAL DATA · EVIDENCE READY</div><h1>洞察报告 <span>一目了然。</span></h1><p>每份分析都包含清晰口径、证据引用和可追溯的运行记录。</p></div><button class="primary-action interactive" type="button" @click="downloadReport"><Download :size="14" />导出最新报告</button></section>
          <section class="panel report-hero"><div class="report-copy"><span class="report-label"><Sparkles :size="13" />真实数据简报 · {{ overview?.period_label ?? "等待数据源" }}</span><h2>{{ latestQuestion }}</h2><p>{{ aiConclusion }}</p><div class="report-meta"><span><Database :size="13" />{{ analysisSource }}</span><span><ShieldCheck :size="13" />指标由真实数据源即时聚合</span></div><button type="button" class="primary-action interactive" @click="downloadReport"><FileText :size="14" />导出完整报告</button></div><div class="report-art"><div class="report-chart-head"><span><BarChart3 :size="13" />分析图表</span><em>{{ reportChartPayload?.summary ?? "真实查询结果" }}</em></div><div v-if="reportChartPayload" ref="reportChartHost" class="report-chart" role="img" :aria-label="reportChartPayload.summary" /><div v-else class="report-chart-empty"><BarChart3 :size="18" /><span>{{ reportChartLoading ? "正在从查询产物生成图表…" : reportChartNote }}</span></div><div class="report-chart-foot"><span>{{ reportChartPayload?.note ?? "图表由本次受控 SQL 查询结果生成" }}</span><button v-if="reportRun" type="button" class="interactive" @click="selectSection('query')">继续分析 <ArrowUpRight :size="12" /></button></div></div></section>
          <section class="panel followup-panel"><header class="panel-heading"><div><div class="panel-kicker">CONTEXT FOLLOW-UP</div><h2>继续追问这份报告</h2></div><span class="followup-context"><MessageSquareText :size="12" />{{ followupContext }}</span></header><div class="followup-thread"><div v-for="message in followupMessages" :key="message.id" class="followup-item" :class="message.role"><small>{{ message.role === "user" ? "你" : "智析" }}</small><p>{{ message.content_text }}</p></div><div v-if="followupPending" class="followup-item user"><small>你</small><p>{{ pendingFollowupQuestion }}</p></div><div v-if="followupPending" class="followup-item assistant pending"><small>智析</small><p>正在沿用当前会话上下文继续查询真实数据…</p></div><div v-if="followupError" class="followup-item assistant error"><small>智析</small><p>{{ followupError }}</p></div><div v-if="!followupMessages.length && !followupPending && !followupError" class="followup-empty"><span>在上方智能问数中完成一次分析后，就可以在这里基于报告继续追问。</span></div></div><div class="followup-input-row"><textarea ref="followupInput" v-model="followupQuestion" rows="1" placeholder="基于当前报告继续追问，例如：按流量类型拆分呢？" @keydown.enter.exact.prevent="askFollowUp" /><button type="button" class="send-button interactive" :disabled="!followupQuestion.trim() || followupPending || !followupReady" :aria-label="followupPending ? '追问分析中' : '发送追问'" @click="askFollowUp"><span v-if="followupPending" class="spinner" /><Send v-else :size="15" /></button></div><div class="followup-foot"><span>追问会沿用当前会话与数据源</span><span>{{ followupReady ? "Agent 已就绪" : "请先在智能问数中完成一次分析" }}</span></div></section>
          <section class="panel table-panel"><header class="panel-heading"><div><div class="panel-kicker">ANALYSIS HISTORY</div><h2>最近的分析会话</h2></div><button type="button" class="outline-action interactive" @click="sessions.load()"><RefreshCw :size="14" />刷新</button></header><div v-if="reportRows.length" class="data-table"><div class="table-row table-head"><span>报告名称</span><span>数据源</span><span>生成时间</span><span>状态</span><span /></div><button v-for="row in reportRows" :key="row.id" type="button" class="table-row interactive" @click="openReport(row.id)"><span class="report-name"><i><FileText :size="15" /></i><strong>{{ row.title }}</strong></span><span>{{ row.type }}</span><span>{{ row.time }}</span><span class="success-state"><Check :size="13" />可回放</span><ArrowUpRight :size="15" /></button></div><div v-else class="data-empty table-empty"><FileText :size="20" /><strong>暂无真实分析报告</strong><span>在智能问数中发起一次真实分析后，会话与证据链会自动出现在这里。</span><button type="button" class="outline-action interactive" @click="selectSection('query')">去提问</button></div></section>
        </template>

        <template v-else-if="activeSection === 'ledger'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />DATA ASSET LEDGER</div><h1>数据资产台账 <span>资产清晰。</span></h1><p>集中查看已接入数据源、Schema 状态与真实记录规模。</p></div><button type="button" class="primary-action interactive" @click="openDatasources"><Plus :size="14" />接入数据源</button></section>
          <section class="stat-grid"><article v-for="stat in ledgerStats" :key="stat.label" class="panel stat-card"><span>{{ stat.label }}</span><strong>{{ stat.value }}</strong><small :class="stat.tone">{{ stat.note }}</small></article></section>
          <section class="panel table-panel"><header class="panel-heading"><div><div class="panel-kicker">ACTIVE ASSETS</div><h2>数据源清单</h2></div><button type="button" class="outline-action interactive" @click="datasources.load()"><RefreshCw :size="14" />同步台账</button></header><div v-if="ledgerRows.length" class="data-table ledger-table"><div class="ledger-row table-head"><span>数据源名称</span><span>类型 / 字段</span><span>当前状态</span><span>真实记录数</span><span>最近检查</span></div><button v-for="row in ledgerRows" :key="row.id" type="button" class="ledger-row interactive" @click="openDatasources"><span class="ledger-name"><i :class="row.color" /><strong>{{ row.name }}</strong></span><span>{{ row.type }}</span><span><em class="stage-pill">{{ row.status }}</em></span><span>{{ row.rows }}</span><span>{{ row.checkedAt }}</span></button></div><div v-else class="data-empty table-empty"><Database :size="20" /><strong>尚未接入数据资产</strong><span>上传真实 CSV 或连接 MySQL 后，台账会自动展示 Schema 与记录规模。</span><button type="button" class="outline-action interactive" @click="openDatasources">去接入</button></div></section>
          <section class="panel insight-note"><i><Lightbulb :size="16" /></i><div><strong>资产状态</strong><p>{{ ledgerNote }}</p></div><em><ShieldCheck :size="13" />真实口径</em></section>
        </template>

        <template v-else-if="activeSection === 'finance'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />FINANCE OVERVIEW</div><h1>收支管理 <span>收支一目了然。</span></h1><p>聚合收入、成本和现金流，及时发现经营变化。</p></div><button type="button" class="primary-action interactive" @click="openUpload"><Upload :size="14" />导入流水</button></section>
          <section class="panel data-empty finance-empty"><Wallet :size="24" /><strong>当前接入的数据源不含收支字段</strong><span>UCI 银行营销与在线商店数据不包含收入、成本或支付状态。接入含金额与支付状态的财务数据后，此页会自动生成现金流与收支分析。</span><button type="button" class="outline-action interactive" @click="openDatasources">查看当前数据资产</button></section>
        </template>
      </div></div>
    </main>
    <Transition name="toast-spring"><div v-if="toast" class="toast" :class="'toast-' + toast.kind"><span><Check v-if="toast.kind === 'success'" :size="14" /><AlertTriangle v-else-if="toast.kind === 'warning'" :size="14" /><Sparkles v-else :size="14" /></span>{{ toast.message }}<button type="button" aria-label="关闭提示" @click="toast = null">×</button></div></Transition>
    <input ref="fileInput" class="visually-hidden" type="file" accept=".csv,.xlsx,.xls,.sqlite,.db" @change="handleFileSelected" />
  </section>
</template>
