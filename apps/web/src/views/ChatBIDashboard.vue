<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import type { ECharts, EChartsOption } from "echarts";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, Bell, BrainCircuit,
  Check, ChevronDown, CircleHelp, Clock3, Database, Download, FileSpreadsheet, FileText, Layers,
  LayoutDashboard, Lightbulb, LogOut, MessageSquareText, Moon, MoreHorizontal, Plus, RefreshCw,
  Send, Settings2, ShieldCheck, Sparkles, Stethoscope, Sun, TrendingUp, Upload, Wallet,
} from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import AskAnswerChart from "@/components/AskAnswerChart.vue";
import { getArtifactContent } from "@/api/artifacts";
import { buildApiUrl } from "@/api/client";
import { getDiagnosisCapabilities, parseDiagnosisQuestion, runDiagnosis } from "@/api/diagnosis";
import type {
  DiagnosisCapabilities,
  DiagnosisHypothesis,
  DiagnosisIntent,
  DiagnosisResult,
} from "@/api/diagnosis";
import { getDatasetOverview } from "@/api/datasources";
import { listRunArtifacts } from "@/api/runs";
import { isSafeChartMime } from "@/lib/artifactContent";
import type { DatasetOverview, Run, Scalar, TableData } from "@/api/types";
import { downloadCsv, downloadText, rowsToCsv, safeFilename, todayStamp } from "@/lib/dataExport";
import { buildReportChart, chartScore } from "@/lib/reportChart";
import type { ReportChartPayload } from "@/lib/reportChart";
import { useTheme } from "@/lib/theme";
import { useDatasourceStore } from "@/stores/datasourceStore";
import { useAuthStore } from "@/stores/authStore";
import { useModelStore } from "@/stores/modelStore";
import { useRunStore } from "@/stores/runStore";
import { useSessionStore } from "@/stores/sessionStore";

type Section = "dashboard" | "query" | "reports" | "diagnosis" | "ledger" | "finance";
type ToastKind = "success" | "info" | "warning";

interface AppNotification {
  id: string;
  title: string;
  detail: string;
  kind: ToastKind;
  section: Section | null;
  createdAt: number;
  read: boolean;
}
type InsightKind = "positive" | "warning" | "neutral";

interface InsightCard {
  kind: InsightKind;
  label: string;
  title: string;
  detail: string;
  time: string;
}

const router = useRouter();
const route = useRoute();
const { isDark, toggleTheme } = useTheme();
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
const notifications = ref<AppNotification[]>([]);
const notificationOpen = ref(false);
let notificationSeq = 0;
const seededAlertKeys = new Set<string>();
const syncedDatasourceIds = new Set<string>();
const unreadCount = computed(() => notifications.value.filter((item) => !item.read).length);
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
const reportChartImage = ref<string | null>(null);
const reportChartLoading = ref(false);
const reportChartNote = ref("完成一次真实分析后，会从查询结果自动生成图表");
const followupQuestion = ref("");
const followupPending = ref(false);
const followupError = ref<string | null>(null);
const followupInput = ref<HTMLTextAreaElement | null>(null);
const followupThread = ref<HTMLElement | null>(null);
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
const diagnosisCapabilities = ref<DiagnosisCapabilities | null>(null);
const diagnosisCapabilitiesLoading = ref(false);
const diagnosisRunning = ref(false);
const diagnosisError = ref<string | null>(null);
const diagnosisResult = ref<DiagnosisResult | null>(null);
const diagnosisMetric = ref("");
const diagnosisDimension = ref("");
const diagnosisTime = ref("");
const diagnosisTopN = ref(6);
const diagnosisTechnicalOpen = ref(false);
const diagnosisQuestion = ref("");
const diagnosisIntent = ref<DiagnosisIntent | null>(null);
const diagnosisAsking = ref(false);
const diagnosisHost = ref<HTMLElement | null>(null);
let diagnosisChart: ECharts | null = null;
let diagnosisResizeObserver: ResizeObserver | null = null;

const navItems = [
  { id: "dashboard" as const, label: "经营驾驶舱", icon: LayoutDashboard },
  { id: "ask" as const, label: "智能工作台", icon: Sparkles },
  { id: "query" as const, label: "智能问数", icon: MessageSquareText },
  { id: "reports" as const, label: "洞察报告", icon: FileText },
  { id: "diagnosis" as const, label: "经营诊断", icon: Stethoscope },
  { id: "ledger" as const, label: "数据资产台账", icon: Layers },
  { id: "finance" as const, label: "收支管理", icon: Wallet },
];
const darkChartPalette = ["#43d7f5", "#6889ff", "#9b7aff", "#39cda7", "#f2b566", "#e57e9c", "#7dd3fc", "#c4b5fd"];
const lightChartPalette = ["#5b6bef", "#7d5bee", "#4c9bff", "#2f9e7a", "#b56f12", "#c45b7a", "#5f8fd8", "#9b7aff"];
const chartPalette = computed(() => (isDark.value ? darkChartPalette : lightChartPalette));
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
  diagnosis: "经营诊断",
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
const diagnosisReady = computed(() => diagnosisCapabilities.value?.ready === true);
const diagnosisNarrativeBlocks = computed(() => {
  const blocks: Array<{ type: "heading" | "item" | "text"; text: string }> = [];
  const narrative = diagnosisResult.value?.narrative ?? "";
  for (const line of narrative.split("\n")) {
    const text = line.trim();
    if (!text) continue;
    if (text.startsWith("## ")) blocks.push({ type: "heading", text: text.slice(3) });
    else if (text.startsWith("- ")) blocks.push({ type: "item", text: text.slice(2) });
    else blocks.push({ type: "text", text });
  }
  return blocks;
});
const diagnosisDrivers = computed(() => {
  const contributions = diagnosisResult.value?.contributions ?? [];
  const drag = [...contributions]
    .filter((item) => item.delta < 0)
    .sort((left, right) => left.delta - right.delta)[0] ?? null;
  const lift = [...contributions]
    .filter((item) => item.delta > 0)
    .sort((left, right) => right.delta - left.delta)[0] ?? null;
  return { drag, lift };
});
const diagnosisHeadline = computed(() => {
  const result = diagnosisResult.value;
  if (result === null) return "";
  const period = result.period;
  const metric = result.metric_label;
  if (period.delta === 0) {
    return `${period.current_label}${metric}为 ${formatMetric(period.current_total)}，与${period.baseline_label}持平。`;
  }
  const direction = period.delta > 0 ? "多" : "少";
  const percent = period.delta_pct === null
    ? ""
    : `（${period.delta_pct > 0 ? "+" : ""}${period.delta_pct.toFixed(2)}%）`;
  let sentence = `${period.current_label}${metric} ${formatMetric(period.current_total)}，` +
    `比${period.baseline_label}${direction} ${formatMetric(Math.abs(period.delta))}${percent}。`;
  const { drag, lift } = diagnosisDrivers.value;
  if (period.delta < 0) {
    if (drag) sentence += `${drag.group}减少 ${formatMetric(Math.abs(drag.delta))}，是主要拖累；`;
    if (lift) sentence += `${lift.group}增加 ${formatMetric(lift.delta)}，抵消了部分降幅。`;
  } else {
    if (lift) sentence += `${lift.group}增加 ${formatMetric(lift.delta)}，是主要拉动；`;
    if (drag) sentence += `${drag.group}减少 ${formatMetric(Math.abs(drag.delta))}，抵消了部分增幅。`;
  }
  return sentence;
});
const diagnosisVerificationText = computed(() => {
  const verification = diagnosisResult.value?.verification;
  if (!verification) return "";
  if (verification.status === "valid") return "关键核对全部通过";
  if (verification.status === "invalid") return "有核对项未通过";
  return "数据不足以核对";
});
const diagnosisCheckLabels: Record<string, string> = {
  sum_contributions_equals_delta: "分项变化加总 = 整体变化",
  shares_sum_to_one: "各项占比合计为 100%",
  both_periods_have_rows: "本期和上期都有数据",
  dimension_missing_within_limit: "分组字段缺失不超过 5%",
};
const diagnosisMethodLabels: Record<string, string> = {
  additive_decomposition: "分项贡献相加",
  temporal_stability: "多期方向一致性",
};
const diagnosisSuggestions = computed(() => {
  const capabilities = diagnosisCapabilities.value;
  if (capabilities === null || !capabilities.ready) return [];
  const metric = capabilities.measures.find((item) => item.name === capabilities.default_measure)?.label
    ?? capabilities.measures[0]?.label
    ?? "营收";
  const dimension = capabilities.dimensions.find((item) => item.name === capabilities.default_dimension)?.label
    ?? capabilities.dimensions[0]?.label
    ?? "区域";
  return [
    `本月${metric}为什么下降？按${dimension}看看`,
    `哪个${dimension}对${metric}影响最大？`,
    `上个月${metric}变化了多少？`,
  ];
});
const diagnosisAskPlaceholder = computed(
  () => diagnosisSuggestions.value[0] ?? "例如：本月营收为什么下降？按区域看看",
);
const reportRun = computed<Run | null>(() => {
  const live = runs.currentRun;
  if (live?.status === "succeeded" && live.session_id === sessions.currentSession?.id) return live;
  return sessions.runs.find((run) => run.status === "succeeded") ?? null;
});
const followupMessages = computed(() =>
  sessions.messages.filter((message) => message.content_text.trim()).slice(-6),
);
const followupChartMessageId = computed(() => {
  const latest = [...followupMessages.value].reverse().find((message) => message.role === "assistant" && message.run_id);
  return latest?.id ?? null;
});
const followupContext = computed(() => sessions.currentSession?.title ?? "尚无分析会话");
const followupReady = computed(() => liveAgentReady.value && sessions.currentSession !== null);

interface NotifyOptions {
  title?: string;
  section?: Section;
  /** 默认只记录 success / warning；重要 info 可显式要求入列表。 */
  record?: boolean;
}

const DEFAULT_NOTIFICATION_TITLES: Record<ToastKind, string> = {
  success: "操作完成",
  warning: "需要注意",
  info: "消息提示",
};

function pushNotification(
  title: string,
  detail: string,
  kind: ToastKind,
  section: Section | null = null,
) {
  const duplicate = notifications.value.find(
    (item) => item.title === title && item.detail === detail && !item.read,
  );
  if (duplicate) return;
  notificationSeq += 1;
  notifications.value = [
    {
      id: "notif_" + Date.now() + "_" + notificationSeq,
      title,
      detail,
      kind,
      section,
      createdAt: Date.now(),
      read: false,
    },
    ...notifications.value,
  ].slice(0, 30);
}

function notify(message: string, kind: ToastKind = "success", options: NotifyOptions = {}) {
  toast.value = { message, kind };
  if (toastTimer !== null) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.value = null; }, 2800);
  const record = options.record ?? kind !== "info";
  if (record) {
    pushNotification(
      options.title ?? DEFAULT_NOTIFICATION_TITLES[kind],
      message,
      kind,
      options.section ?? null,
    );
  }
}

function formatNotificationTime(timestamp: number) {
  const elapsed = Date.now() - timestamp;
  if (elapsed < 60_000) return "刚刚";
  if (elapsed < 3_600_000) return Math.floor(elapsed / 60_000) + " 分钟前";
  if (elapsed < 86_400_000) return Math.floor(elapsed / 3_600_000) + " 小时前";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

function toggleNotificationList() {
  notificationOpen.value = !notificationOpen.value;
  profileOpen.value = false;
}

// 顶栏的 backdrop-filter 会让 fixed 遮罩以顶栏为包含块，因此再挂一个文档级监听，
// 保证点击页面任意位置都能收起消息列表。
function handleDocumentPointerDown(event: PointerEvent) {
  if (!notificationOpen.value) return;
  const target = event.target;
  if (target instanceof Element && target.closest(".notification-wrap")) return;
  notificationOpen.value = false;
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && notificationOpen.value) {
    notificationOpen.value = false;
  }
}

function markAllNotificationsRead() {
  notifications.value = notifications.value.map((item) => ({ ...item, read: true }));
}

function clearReadNotifications() {
  notifications.value = notifications.value.filter((item) => !item.read);
}

function openNotification(item: AppNotification) {
  notifications.value = notifications.value.map((entry) =>
    entry.id === item.id ? { ...entry, read: true } : entry,
  );
  notificationOpen.value = false;
  if (item.section !== null) selectSection(item.section);
}
function handleNavSelect(id: Section | "ask") {
  if (id === "ask") {
    void router.push({
      path: "/ask",
      query: datasourceReady.value ? { workspace: datasourceReady.value.id } : {},
    });
    return;
  }
  selectSection(id);
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
    if (!syncedDatasourceIds.has(source.id)) {
      syncedDatasourceIds.add(source.id);
      pushNotification(
        "数据源已同步",
        data.datasource_name + " · " + formatCount(data.row_count) + " 条记录 · Schema v" + data.schema_revision,
        "info",
        "dashboard",
      );
    }
    for (const alert of data.alerts) {
      const key = source.id + "::" + alert.title;
      if (seededAlertKeys.has(key)) continue;
      seededAlertKeys.add(key);
      pushNotification(alert.title, alert.detail, alert.level, "dashboard");
    }
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
  notify(overview.value ? "真实数据聚合并已刷新" : "真实数据刷新失败", overview.value ? "success" : "warning", {
    record: overview.value === null,
  });
}
function renderCharts() {
  const data = overview.value;
  const light = !isDark.value;
  const ink = light ? "#172454" : "#e6f4ff";
  const muted = light ? "#5f6d92" : "#7486a1";
  const subtle = light ? "#8794b5" : "#6f829d";
  const tooltipBg = light ? "rgba(255,255,255,.98)" : "rgba(8,19,39,.96)";
  const tooltipBorder = light ? "#dfe7f7" : "rgba(77,190,255,.25)";
  const splitLine = light ? "rgba(23,36,84,.08)" : "rgba(104,153,199,.1)";
  const axisLine = light ? "#dfe7f7" : "rgba(120,165,206,.18)";
  const linePrimary = light ? "#5b6bef" : "#53d6ff";
  const lineSecondary = light ? "#7d5bee" : "#a08cff";
  const pointBorder = light ? "#ffffff" : "#071a30";
  const barTop = light ? "#5b6bef" : "#43d7f5";
  const barBottom = light ? "rgba(91,107,239,.18)" : "rgba(45,186,255,.18)";
  const barHover = light ? "#7d5bee" : "#8ceaff";
  const pieBorder = light ? "#ffffff" : "#0a1730";
  const rankBg = light ? "rgba(91,107,239,.08)" : "rgba(81,129,184,.09)";
  const rankStart = light ? "#5b6bef" : "#38bdf8";
  const rankEnd = light ? "#7d5bee" : "#8b7bff";
  const rankLabel = light ? "#5f6d92" : "#92a9c5";
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
          itemStyle: { borderRadius: [4, 4, 0, 0], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: barTop }, { offset: 1, color: barBottom }]) },
          emphasis: { itemStyle: { color: barHover } },
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
        lineStyle: { width: 2.5, color: index === 0 ? linePrimary : lineSecondary },
        itemStyle: { color: index === 0 ? linePrimary : lineSecondary, borderColor: pointBorder, borderWidth: 2 },
      };
    });
    const yAxis = [
      { type: "value" as const, name: "条", min: 0, splitNumber: 4, axisLabel: { color: subtle, fontSize: 11 }, splitLine: { lineStyle: { color: splitLine, type: "dashed" as const } }, axisLine: { show: false } },
      ...(hasRate ? [{ type: "value" as const, name: "%", min: 0, max: rateMax, splitNumber: 4, axisLabel: { color: light ? "#6d4fd8" : "#8b7fd8", fontSize: 11, formatter: "{value}%" }, splitLine: { show: false }, axisLine: { show: false } }] : []),
    ];
    trendChart?.setOption({
      animationDuration: 900,
      grid: { left: 5, right: hasRate ? 36 : 14, top: 16, bottom: 30, containLabel: true },
      legend: { show: false },
      tooltip: {
        trigger: "axis",
        backgroundColor: tooltipBg,
        borderColor: tooltipBorder,
        textStyle: { color: ink, fontSize: 12 },
        formatter: (raw: unknown) => {
          const items = raw as Array<{ marker: string; seriesName: string; value: number; seriesIndex: number }>;
          const series = data.trend?.series ?? [];
          return items.map((item) => item.marker + item.seriesName + "：" + Number(item.value).toLocaleString("zh-CN") + (series[item.seriesIndex]?.axis === "rate" ? "%" : " 条")).join("<br/>");
        },
      },
      xAxis: { type: "category", data: data.trend.labels, axisLine: { lineStyle: { color: axisLine } }, axisTick: { show: false }, axisLabel: { color: muted, fontSize: 12, margin: 10 } },
      yAxis,
      series: chartSeries,
    } as EChartsOption, { notMerge: true });
  }
  if (channelHost.value && data?.distribution) {
    channelChart?.setOption({
      animationDuration: 900,
      tooltip: { trigger: "item", backgroundColor: tooltipBg, borderColor: tooltipBorder, textStyle: { color: ink, fontSize: 11 }, formatter: "{b} · {d}%" },
      color: chartPalette.value,
      series: [{ type: "pie", radius: ["63%", "84%"], center: ["50%", "50%"], label: { show: false }, labelLine: { show: false }, itemStyle: { borderColor: pieBorder, borderWidth: 3, borderRadius: 5 }, emphasis: { scale: true, scaleSize: 7 }, data: data.distribution.items.map((item) => ({ value: item.count, name: item.name })) }],
      graphic: [
        { type: "text", left: "center", top: "39%", style: { text: formatCount(data.row_count) + " 条", fill: ink, fontSize: 17, fontWeight: 700, fontFamily: "Inter,sans-serif" } },
        { type: "text", left: "center", top: "58%", style: { text: data.distribution.label, fill: muted, fontSize: 10.5, fontFamily: "Inter,sans-serif" } },
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
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: tooltipBg, borderColor: tooltipBorder, textStyle: { color: ink, fontSize: 11 }, valueFormatter: (value) => Number(value).toFixed(1) + "%" },
      xAxis: { type: "value", max: maxValue, show: false },
      yAxis: { type: "category", inverse: true, data: data.ranking.items.map((item) => item.name), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: rankLabel, fontSize: 11.5, margin: 12 } },
      series: [{ type: "bar", data: values, barWidth: 11, showBackground: true, backgroundStyle: { color: rankBg, borderRadius: 99 }, itemStyle: { borderRadius: 99, color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: rankStart }, { offset: 1, color: rankEnd }]) }, label: { show: true, position: "right", color: rankLabel, fontSize: 10.5, formatter: "{c}%" } }],
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
watch(isDark, async () => {
  await nextTick();
  initCharts();
  initDiagnosisChart();
});
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
function clearReportChartImage() {
  if (reportChartImage.value !== null) {
    URL.revokeObjectURL(reportChartImage.value);
    reportChartImage.value = null;
  }
}
function scrollFollowupToEnd() {
  const element = followupThread.value;
  if (element !== null) element.scrollTop = element.scrollHeight;
}
async function loadReportChart() {
  const run = reportRun.value;
  if (run === null) {
    reportChartRunId = null;
    reportChartPayload.value = null;
    clearReportChartImage();
    reportChartNote.value = "完成一次真实分析后，会从查询结果自动生成图表";
    initReportChart();
    return;
  }
  if (reportChartRunId === run.id && (reportChartPayload.value !== null || reportChartImage.value !== null)) {
    await nextTick();
    initReportChart();
    return;
  }
  reportChartRunId = run.id;
  reportChartLoading.value = true;
  try {
    const artifacts = await listRunArtifacts(run.id);
    // 追问/分析生成的图表产物优先直接展示，没有时再用表格结果兜底绘图。
    const chartArtifact = artifacts.find((item) => item.type === "chart");
    if (chartArtifact !== undefined) {
      const content = await getArtifactContent(chartArtifact.id);
      if (isSafeChartMime(content.contentType)) {
        clearReportChartImage();
        reportChartImage.value = URL.createObjectURL(content.blob);
        reportChartPayload.value = null;
        reportChartNote.value = chartArtifact.title || "来自本次分析的图表产物";
        await nextTick();
        initReportChart();
        return;
      }
    }
    clearReportChartImage();
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
    clearReportChartImage();
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
    notify("分析任务已提交，正在生成证据链", "info", {
      title: "智能问数 · 已提交",
      section: "query",
      record: true,
    });
  } catch (error) {
    isAnalyzing.value = false;
    const message = error instanceof Error ? error.message : "分析任务提交失败";
    aiConclusion.value = "分析任务提交失败：" + message;
    analysisSource.value = "运行未启动";
    notify(message, "warning");
  }
}
function overviewSections(): { title: string; header: string[]; rows: Scalar[][] }[] {
  const data = overview.value;
  if (data === null) return [];
  const sections: { title: string; header: string[]; rows: Scalar[][] }[] = [];
  sections.push({
    title: "概览",
    header: ["数据源", "数据表", "记录数", "字段数", "整体转化率", "统计周期", "更新时间"],
    rows: [[data.datasource_name, data.table, data.row_count, data.column_count,
      data.conversion_pct === null ? "—" : `${data.conversion_pct}%`, data.period_label, formatDateTime(data.updated_at)]],
  });
  if (data.metrics.length > 0) {
    sections.push({
      title: "核心指标",
      header: ["指标", "数值", "说明", "环比"],
      rows: data.metrics.map((metric) => [metric.label, metric.value, metric.detail, metric.change ?? "—"]),
    });
  }
  const trend = data.trend;
  if (trend !== null && trend.labels.length > 0) {
    sections.push({
      title: `月度趋势 · ${trend.title}`,
      header: ["维度", ...trend.series.map((item) => item.name)],
      rows: trend.labels.map((label, index) => [label, ...trend.series.map((item) => item.values[index] ?? null)]),
    });
  }
  for (const group of [data.distribution, data.ranking]) {
    if (group === null) continue;
    sections.push({
      title: `${group.title} · ${group.column}`,
      header: ["分组", "记录数", "占比", "转化率"],
      rows: group.items.map((item) => [item.name, item.count, `${item.share_pct}%`, item.conversion_pct === null ? "—" : `${item.conversion_pct}%`]),
    });
  }
  if (data.alerts.length > 0) {
    sections.push({
      title: "数据预警",
      header: ["级别", "标题", "说明"],
      rows: data.alerts.map((alert) => [alert.level === "warning" ? "关注" : "提示", alert.title, alert.detail]),
    });
  }
  return sections;
}

function exportDashboardCsv() {
  const sections = overviewSections();
  if (sections.length === 0) {
    notify("暂无可导出的看板数据", "info");
    return;
  }
  const csv = sections
    .map((section) => [`# ${section.title}`, rowsToCsv([section.header, ...section.rows])].join("\r\n"))
    .join("\r\n\r\n");
  const source = overview.value?.datasource_name ?? "经营看板";
  downloadCsv(`${safeFilename(source)}-看板数据-${todayStamp()}.csv`, csv);
  notify("看板数据已导出为 CSV");
}

function buildReportMarkdown(): string {
  const data = overview.value;
  const lines: string[] = [];
  lines.push("# 智析 ChatBI · 经营洞察报告", "");
  lines.push(`生成时间：${new Date().toLocaleString("zh-CN")}`);
  if (data !== null) {
    lines.push(`数据来源：${data.datasource_name} · ${data.table}`);
    lines.push(`数据规模：${formatCount(data.row_count)} 条记录 · ${data.column_count} 个字段`);
    lines.push(`统计周期：${data.period_label}`);
    if (data.conversion_pct !== null) lines.push(`整体转化率：${data.conversion_pct}%`);
  }
  lines.push("", "## 分析问题", "", latestQuestion.value || "—");
  lines.push("", "## 核心结论", "", aiConclusion.value || "—");
  for (const section of overviewSections()) {
    if (section.title === "概览") continue;
    lines.push("", `## ${section.title}`, "");
    lines.push(`| ${section.header.join(" | ")} |`);
    lines.push(`| ${section.header.map(() => "---").join(" | ")} |`);
    for (const row of section.rows) {
      lines.push(`| ${row.map((cell) => cell === null || cell === undefined ? "—" : String(cell)).join(" | ")} |`);
    }
  }
  lines.push("", "## 口径说明", "", `- ${analysisSource.value}`);
  lines.push(`- 指标由真实数据源即时聚合，导出时间 ${new Date().toLocaleString("zh-CN")}`);
  lines.push("- 请结合企业数据口径与证据材料复核本报告");
  return lines.join("\n");
}

function downloadReport() {
  const data = overview.value;
  const name = data === null ? "智析经营洞察" : `${safeFilename(data.datasource_name)}-经营洞察`;
  downloadText(`${name}-${todayStamp()}.md`, buildReportMarkdown(), "text/markdown");
  notify("洞察报告已导出为 Markdown（含指标、分组与趋势数据）");
}

function exportReportCsv() {
  const sections = overviewSections().filter((section) => section.title !== "概览");
  if (sections.length === 0) {
    notify("暂无可导出的分析数据", "info");
    return;
  }
  const csv = sections
    .map((section) => [`# ${section.title}`, rowsToCsv([section.header, ...section.rows])].join("\r\n"))
    .join("\r\n\r\n");
  const prefix = overview.value === null ? "智析洞察报告" : `${safeFilename(overview.value.datasource_name)}-洞察报告`;
  downloadCsv(`${prefix}-${todayStamp()}.csv`, csv);
  notify("报告数据已导出为 CSV");
}
function formatMetric(value: number) {
  const absolute = Math.abs(value);
  if (absolute >= 10000) return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  if (absolute >= 100) return value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}
function diagnosisStatusLabel(status: string) {
  const labels: Record<string, string> = {
    leading: "最可能",
    supporting: "有可能",
    contradicted: "存在反向信号",
    rejected: "已排除",
    unknown: "证据不足",
    valid: "核对通过",
    invalid: "核对未通过",
    insufficient: "数据不足",
  };
  return labels[status] ?? status;
}
function diagnosisCheckLabel(name: string) {
  return diagnosisCheckLabels[name] ?? name;
}
function diagnosisMethodLabel(name: string) {
  return diagnosisMethodLabels[name] ?? name;
}
function formatSigned(value: number) {
  return (value >= 0 ? "+" : "") + formatMetric(value);
}
function hypothesisPlainText(hypothesis: DiagnosisHypothesis) {
  const result = diagnosisResult.value;
  if (result === null) return hypothesis.text;
  const evidence = result.evidence.find((item) => hypothesis.supporting.includes(item.id));
  const group = evidence?.group;
  if (group === undefined) return hypothesis.text;
  const contribution = result.contributions.find((item) => item.group === group)
    ?? (result.others?.group === group ? result.others : null);
  if (contribution === null) return hypothesis.text;
  const direction = contribution.delta >= 0 ? "增加" : "减少";
  const amount = formatMetric(Math.abs(contribution.delta));
  const { drag, lift } = diagnosisDrivers.value;
  if (drag?.group === group) {
    return result.period.delta < 0
      ? `「${group}」${direction} ${amount}，是整体下降的主要拖累。`
      : `「${group}」${direction} ${amount}，拉低了整体增幅。`;
  }
  if (lift?.group === group) {
    return result.period.delta < 0
      ? `「${group}」${direction} ${amount}，抵消了部分降幅。`
      : `「${group}」${direction} ${amount}，是整体增长的主要拉动。`;
  }
  return `「${group}」${direction} ${amount}，对整体变化形成${
    contribution.delta * result.period.delta >= 0 ? "同向" : "反向"
  }影响。`;
}
function hypothesisEvidenceSummary(hypothesis: DiagnosisHypothesis) {
  const against = hypothesis.contradicting.length;
  return `依据 ${hypothesis.supporting.length} 条数据信号` +
    (against > 0 ? `，另有 ${against} 条反向信号` : "");
}
function clearDiagnosisIntent() {
  diagnosisIntent.value = null;
}
async function askDiagnosis() {
  const source = datasourceReady.value;
  const question = diagnosisQuestion.value.trim();
  if (source === null) {
    notify("请先在数据资产中连接真实数据源", "warning");
    return;
  }
  if (!question || diagnosisAsking.value) return;
  if (!diagnosisReady.value) {
    notify(diagnosisCapabilities.value?.message ?? "当前数据源暂不可诊断", "warning");
    return;
  }
  diagnosisAsking.value = true;
  diagnosisError.value = null;
  try {
    const intent = await parseDiagnosisQuestion(source.id, question);
    diagnosisIntent.value = intent;
    if (
      !intent.understood
      || intent.metric === null
      || intent.dimension === null
      || intent.time_column === null
    ) {
      notify(intent.clarification ?? "没有识别出可诊断的问题，请换个说法", "warning");
      return;
    }
    diagnosisMetric.value = intent.metric;
    diagnosisDimension.value = intent.dimension;
    diagnosisTime.value = intent.time_column;
    await nextTick();
    await executeDiagnosis();
  } catch (error) {
    diagnosisIntent.value = null;
    diagnosisError.value = error instanceof Error ? error.message : "问题解析失败";
    notify(diagnosisError.value, "warning");
  } finally {
    diagnosisAsking.value = false;
  }
}
function applyDiagnosisQuestion(text: string) {
  diagnosisQuestion.value = text;
  void askDiagnosis();
}
async function loadDiagnosis(force = false) {
  const source = datasourceReady.value;
  diagnosisError.value = null;
  if (source === null) {
    diagnosisCapabilities.value = null;
    diagnosisResult.value = null;
    await nextTick();
    initDiagnosisChart();
    return;
  }
  if (!force && diagnosisCapabilities.value?.datasource_id === source.id) return;
  diagnosisCapabilitiesLoading.value = true;
  diagnosisResult.value = null;
  try {
    const capabilities = await getDiagnosisCapabilities(source.id);
    diagnosisCapabilities.value = capabilities;
    diagnosisMetric.value = capabilities.default_measure ?? capabilities.measures[0]?.name ?? "";
    diagnosisDimension.value = capabilities.default_dimension ?? capabilities.dimensions[0]?.name ?? "";
    diagnosisTime.value = capabilities.default_time_column ?? capabilities.time_columns[0]?.name ?? "";
  } catch (error) {
    diagnosisCapabilities.value = null;
    diagnosisError.value = error instanceof Error ? error.message : "诊断能力识别失败";
  } finally {
    diagnosisCapabilitiesLoading.value = false;
    await nextTick();
    initDiagnosisChart();
  }
}
async function executeDiagnosis() {
  const source = datasourceReady.value;
  if (source === null) {
    notify("请先在数据资产中连接真实数据源", "warning");
    return;
  }
  if (!diagnosisReady.value) {
    notify(diagnosisCapabilities.value?.message ?? "当前数据源暂不可诊断", "warning");
    return;
  }
  if (!diagnosisMetric.value || !diagnosisDimension.value || !diagnosisTime.value) {
    notify("请选择指标、维度与时间字段", "warning");
    return;
  }
  diagnosisRunning.value = true;
  diagnosisError.value = null;
  try {
    const result = await runDiagnosis(source.id, {
      metric: diagnosisMetric.value,
      dimension: diagnosisDimension.value,
      time_column: diagnosisTime.value,
      top_n: diagnosisTopN.value,
    });
    if (datasourceReady.value?.id !== source.id) return;
    diagnosisResult.value = result;
    await nextTick();
    initDiagnosisChart();
    notify("经营诊断完成 · 不变量验证 " + result.verification.passed + "/" + result.verification.total + " 通过", "success", {
      title: "经营诊断 · 已完成",
      section: "diagnosis",
    });
  } catch (error) {
    diagnosisResult.value = null;
    diagnosisError.value = error instanceof Error ? error.message : "经营诊断执行失败";
    notify(diagnosisError.value, "warning");
    await nextTick();
    initDiagnosisChart();
  } finally {
    diagnosisRunning.value = false;
  }
}
function renderDiagnosisChart() {
  const result = diagnosisResult.value;
  if (diagnosisHost.value === null) return;
  if (result === null) {
    diagnosisChart?.clear();
    return;
  }
  const light = !isDark.value;
  const ink = light ? "#172454" : "#e6f4ff";
  const muted = light ? "#5f6d92" : "#7486a1";
  const axisLine = light ? "#dfe7f7" : "rgba(120,165,206,.18)";
  const tooltipBg = light ? "rgba(255,255,255,.98)" : "rgba(8,19,39,.96)";
  const tooltipBorder = light ? "#dfe7f7" : "rgba(77,190,255,.25)";
  const totalColor = light ? "#5b6bef" : "#53d6ff";
  const positiveColor = light ? "#2f9e7a" : "#35d6a5";
  const negativeColor = light ? "#c45b7a" : "#e5677f";
  const labels = ["上期", ...result.chart.labels, "本期"];
  const base: number[] = [0];
  const values: number[] = [result.chart.baseline_total];
  const colors: string[] = [totalColor];
  const signed: Array<number | null> = [null];
  let running = result.chart.baseline_total;
  for (const delta of result.chart.deltas) {
    if (delta >= 0) {
      base.push(running);
      values.push(delta);
    } else {
      base.push(running + delta);
      values.push(-delta);
    }
    colors.push(delta >= 0 ? positiveColor : negativeColor);
    signed.push(delta);
    running += delta;
  }
  base.push(0);
  values.push(result.chart.current_total);
  colors.push(totalColor);
  signed.push(null);
  diagnosisChart?.setOption({
    animationDuration: 900,
    grid: { left: 8, right: 8, top: 22, bottom: 12, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: tooltipBg,
      borderColor: tooltipBorder,
      textStyle: { color: ink, fontSize: 11 },
      formatter: (raw: unknown) => {
        const items = raw as Array<{ dataIndex: number }>;
        const index = items[0]?.dataIndex ?? 0;
        const label = labels[index] ?? "";
        if (index === 0) return label + "<br/>合计：" + formatMetric(result.chart.baseline_total);
        if (index === labels.length - 1) return label + "<br/>合计：" + formatMetric(result.chart.current_total);
        const delta = signed[index] ?? 0;
        const share = result.chart.shares_pct[index - 1];
        const shareText = share === null || share === undefined
          ? ""
          : "<br/>相当于整体变化的 " + share.toFixed(1) + "%";
        return label + "<br/>" + (delta >= 0 ? "拉动 " : "拖累 ") +
          formatMetric(Math.abs(delta)) + shareText;
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: axisLine } },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 10, interval: 0, rotate: labels.length > 6 ? 22 : 0 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: muted, fontSize: 9 },
      splitLine: {
        lineStyle: {
          color: light ? "rgba(23,36,84,.08)" : "rgba(104,153,199,.1)",
          type: "dashed",
        },
      },
      axisLine: { show: false },
    },
    series: [
      {
        name: "base",
        type: "bar",
        stack: "waterfall",
        data: base,
        barWidth: 26,
        silent: true,
        itemStyle: { color: "transparent" },
        emphasis: { itemStyle: { color: "transparent" } },
      },
      {
        name: "value",
        type: "bar",
        stack: "waterfall",
        barWidth: 26,
        data: values.map((value, index) => ({
          value,
          itemStyle: { color: colors[index] ?? totalColor, borderRadius: [4, 4, 0, 0] },
        })),
        label: {
          show: true,
          position: "top",
          color: muted,
          fontSize: 9,
          formatter: (params: unknown) => {
            const item = params as { dataIndex: number; value: number };
            const delta = signed[item.dataIndex];
            return delta === null || delta === undefined
              ? formatMetric(item.value)
              : (delta >= 0 ? "+" : "") + formatMetric(delta);
          },
        },
      },
    ],
  } as EChartsOption, { notMerge: true });
}
function initDiagnosisChart() {
  diagnosisResizeObserver?.disconnect();
  diagnosisChart?.dispose();
  diagnosisChart = null;
  if (diagnosisHost.value === null) return;
  diagnosisChart = echarts.init(diagnosisHost.value);
  renderDiagnosisChart();
  if (typeof ResizeObserver !== "undefined") {
    diagnosisResizeObserver = new ResizeObserver(() => diagnosisChart?.resize());
    diagnosisResizeObserver.observe(diagnosisHost.value);
  }
}
function downloadDiagnosisReport() {
  const result = diagnosisResult.value;
  if (result === null) {
    notify("请先运行一次经营诊断", "info");
    return;
  }
  const lines = [
    "# 智析 ChatBI · 经营诊断报告",
    "",
    "生成时间：" + new Date().toLocaleString("zh-CN"),
    "数据源：" + result.datasource_name + "（" + result.table + "）",
    "诊断口径：" + result.metric_label + " · " + result.dimension_label + " · " + result.time_label,
    "引擎版本：" + result.engine_version + " · 配方 " + result.recipe_id,
    "",
    result.narrative,
    "",
    "## 证据清单",
    ...result.evidence.map((item) =>
      "- " + item.id + " · " + item.claim + "（" + item.method + "，样本 " + item.sample_size + "）"),
    "",
    "## 不变量验证",
    ...result.verification.checks.map((item) =>
      "- " + (item.passed ? "通过" : "未通过") + " · " + item.label + "：" + item.detail),
    "",
    "> 贡献分解只描述数量关系，不构成因果证明。",
  ];
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "智析经营诊断-" + new Date().toISOString().slice(0, 10) + ".md";
  link.click();
  URL.revokeObjectURL(url);
  notify("经营诊断报告已导出为 Markdown");
}

function exportDiagnosisCsv() {
  const result = diagnosisResult.value;
  if (result === null) {
    notify("请先运行一次经营诊断", "info");
    return;
  }
  const period = result.period;
  const sections: { title: string; header: string[]; rows: Scalar[][] }[] = [
    {
      title: "诊断概览",
      header: ["数据源", "数据表", "指标", "分组维度", "时间字段", "引擎版本", "诊断时间"],
      rows: [[result.datasource_name, result.table, result.metric_label, result.dimension_label,
        result.time_label, result.engine_version, result.generated_at]],
    },
    {
      title: "期间对比",
      header: ["对比项", "本期", "上期", "差值", "变化率"],
      rows: [
        [result.metric_label, period.current_total, period.baseline_total, period.delta,
          period.delta_pct === null ? "上期为零，无法计算" : `${period.delta_pct.toFixed(2)}%`],
        ["记录数", period.current_rows, period.baseline_rows, period.current_rows - period.baseline_rows, "—"],
      ],
    },
    {
      title: "贡献分解",
      header: ["分组", "本期", "上期", "差值", "贡献占比", "稳健期数", "一致期数", "状态"],
      rows: [...result.contributions, ...(result.others === null ? [] : [result.others])].map((item) => [
        item.group, item.current_value, item.baseline_value, item.delta,
        item.share_pct === null ? "—" : `${item.share_pct.toFixed(2)}%`, item.robust_periods, item.robust_consistent,
        item.status === "supported" ? "支持" : item.status === "contradicting" ? "反向信号" : "证据不足",
      ]),
    },
    {
      title: "证据清单",
      header: ["编号", "分组", "结论", "数值", "单位", "方法", "样本量", "缺失率", "置信水平", "状态"],
      rows: result.evidence.map((item) => [
        item.id, item.group, item.claim, item.value, item.unit, item.method, item.sample_size,
        `${(item.missing_rate * 100).toFixed(2)}%`, item.confidence_level,
        diagnosisStatusLabel(item.status),
      ]),
    },
    {
      title: "可能原因排序",
      header: ["排序", "假设", "得分", "状态", "支持证据", "反向证据"],
      rows: result.hypotheses.map((item, index) => [
        index + 1, item.text, item.score.toFixed(3), diagnosisStatusLabel(item.status),
        item.supporting.join(" / "), item.contradicting.join(" / "),
      ]),
    },
    {
      title: "结论核对",
      header: ["检查项", "是否通过", "说明", "置信水平"],
      rows: result.verification.checks.map((item) => [
        item.label, item.passed ? "通过" : "未通过", item.detail, item.confidence_level,
      ]),
    },
    {
      title: "数据质量",
      header: ["缺失率", "覆盖率", "缺失单元格", "抽样行数", "新鲜度"],
      rows: [[`${(result.quality.missing_rate * 100).toFixed(2)}%`, `${result.quality.coverage_pct}%`,
        result.quality.missing_cells, result.quality.sampled_rows, result.quality.freshness]],
    },
  ];
  const csv = sections
    .map((section) => [`# ${section.title}`, rowsToCsv([section.header, ...section.rows])].join("\r\n"))
    .join("\r\n\r\n");
  downloadCsv(`${safeFilename(result.datasource_name)}-经营诊断-${todayStamp()}.csv`, csv);
  notify("经营诊断数据已导出为 CSV");
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
  notificationOpen.value = true;
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
  if (section === "diagnosis") {
    await nextTick();
    if (diagnosisCapabilities.value === null && !diagnosisCapabilitiesLoading.value) {
      await loadDiagnosis();
    } else {
      initDiagnosisChart();
    }
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
    if (activeSection.value === "reports") {
      await loadReportChart();
      await nextTick();
      scrollFollowupToEnd();
    }
    if (completion === "partial") {
      notify("分析部分完成，可验证结论与查询产物已保留", "warning", {
        title: "智能问数 · 部分完成",
        section: "reports",
      });
    } else if (completion === "clarification") {
      notify("分析需要补充范围后才能继续", "warning", {
        title: "智能问数 · 需要补充",
        section: "query",
      });
    } else {
      notify("分析完成，结论与证据已更新", "success", {
        title: "智能问数 · 分析完成",
        section: "reports",
      });
    }
  } else {
    const message = runs.currentRun?.error_message ?? "本次分析未能完整完成，请检查数据源配置或查看运行详情。";
    if (wasFollowup) {
      followupError.value = message;
      const sessionId = sessions.currentSession?.id;
      if (sessionId) await sessions.select(sessionId);
      notify("追问未能完成，请查看错误信息", "warning", {
        title: "追问 · 未完成",
        section: "reports",
      });
      return;
    }
    aiConclusion.value = message;
    analysisSource.value = "运行状态 · 请检查执行记录";
    notify("分析结束，请检查运行状态", "warning", {
      title: "智能问数 · 分析未完成",
      section: "reports",
    });
  }
});
onMounted(async () => {
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  document.addEventListener("keydown", handleDocumentKeydown);
  await Promise.allSettled([datasources.load(), models.load(), sessions.load()]);
  const queryWorkspace = route.query.workspace;
  if (typeof queryWorkspace === "string" && readyDatasources.value.some((item) => item.id === queryWorkspace)) {
    preferredDatasourceId.value = queryWorkspace;
  }
  await loadOverview();
  if (preferredDatasourceId.value === null) preferredDatasourceId.value = datasourceReady.value?.id ?? null;
  // 支持从工作台等处通过 /workspace?section=diagnosis 直接落到指定模块。
  const querySection = route.query.section;
  const sections: Section[] = ["dashboard", "query", "reports", "diagnosis", "ledger", "finance"];
  if (typeof querySection === "string" && sections.includes(querySection as Section)) {
    selectSection(querySection as Section);
  }
});
watch(preferredDatasourceId, async () => {
  runInsights.value = null;
  diagnosisCapabilities.value = null;
  diagnosisResult.value = null;
  diagnosisQuestion.value = "";
  diagnosisIntent.value = null;
  await loadOverview();
  if (activeSection.value === "diagnosis") {
    await loadDiagnosis();
  }
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  document.removeEventListener("keydown", handleDocumentKeydown);
  resizeObserver?.disconnect();
  reportResizeObserver?.disconnect();
  diagnosisResizeObserver?.disconnect();
  trendChart?.dispose(); channelChart?.dispose(); regionChart?.dispose();
  reportChart?.dispose();
  diagnosisChart?.dispose();
  clearReportChartImage();
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
        <button v-for="item in navItems" :key="item.id" type="button" class="nav-item interactive" :class="{ active: activeSection === item.id }" @click="handleNavSelect(item.id)"><component :is="item.icon" :size="17" /><span>{{ item.label }}</span><span v-if="item.id === 'reports' && reportRows.length" class="nav-count">{{ reportRows.length }}</span><i v-if="activeSection === item.id" class="nav-active" /></button>
      </nav>
      <div class="side-divider" />
      <div class="side-label side-label-actions"><span>数据资源</span><button type="button" class="tiny-icon interactive" title="导入数据" @click="openUpload"><Plus :size="14" /></button></div>
      <button type="button" class="source-link interactive" @click="openDatasources"><i class="source-dot" /><span class="source-copy"><strong>{{ datasourceLabel }}</strong><small>{{ datasourceMeta }}</small></span><MoreHorizontal :size="15" class="dim" /></button>
      <div class="side-bottom"><div class="engine-card"><div class="engine-heading"><span class="engine-icon"><Sparkles :size="13" /></span><strong>AI 分析引擎</strong><em>{{ liveAgentReady ? "LIVE" : "待配置" }}</em></div><p>{{ liveAgentReady ? activeModel?.model_name + " · 已激活" : "连接真实数据并激活模型" }}</p><div class="engine-meter"><i /></div><small>{{ liveAgentReady ? "Agent · SQL 网关 · DataLink" : "尚未具备真实分析条件" }}</small></div><div class="profile-wrap"><div v-if="profileOpen" class="profile-backdrop" @click="profileOpen = false" /><div v-if="profileOpen" class="profile-popover"><div class="profile-popover-head"><span class="avatar">{{ auth.avatarText }}</span><span class="profile-popover-name"><strong>{{ auth.user?.display_name ?? "未登录" }}</strong><small>{{ auth.roleLabel }} · {{ auth.user?.username ?? "-" }}</small></span></div><div class="profile-row"><span>所属企业</span><strong>{{ auth.enterprise?.name ?? "未绑定企业" }}</strong></div><div class="profile-row"><span>企业 ID</span><strong class="profile-code">{{ auth.enterprise?.code ?? "-" }}</strong></div><button type="button" class="profile-menu-link interactive" @click="openModelSettings"><Settings2 :size="14" />模型与引擎设置</button><button type="button" class="profile-logout-button interactive" @click="handleLogout"><LogOut :size="14" />退出登录</button></div><button type="button" class="profile-link interactive" :class="{ active: profileOpen }" @click="profileOpen = !profileOpen"><span class="avatar">{{ auth.avatarText }}</span><span><strong>{{ auth.user?.display_name ?? "未登录" }}</strong><small>{{ auth.enterprise?.name ?? "未绑定企业" }}</small></span><MoreHorizontal :size="16" /></button></div></div>
    </aside>

    <main class="main-area">
      <header class="topbar"><div class="crumb"><span>工作空间</span><i>/</i><strong>{{ activeTitle }}</strong><span class="realtime"><i />真实数据</span></div><div class="top-actions"><div class="time-label"><i />{{ formatTime(lastUpdated) }} <span>·</span> {{ todayLabel }}</div><button class="icon-action interactive" type="button" title="帮助中心" @click="notify('帮助中心即将开放，欢迎继续探索工作台', 'info')"><CircleHelp :size="17" /></button><button class="icon-action interactive" type="button" title="刷新数据" @click="refreshDashboard"><RefreshCw :size="16" /></button><div class="notification-wrap"><div v-if="notificationOpen" class="notification-backdrop" @click="notificationOpen = false" /><button class="icon-action interactive notification-icon" :class="{ active: notificationOpen }" type="button" :title="unreadCount ? unreadCount + ' 条未读消息' : '消息提醒'" :aria-expanded="notificationOpen" aria-haspopup="dialog" @click="toggleNotificationList"><Bell :size="17" /><span v-if="unreadCount" class="notification-badge">{{ unreadCount > 9 ? "9+" : unreadCount }}</span><i v-else-if="alertCount" class="bell-dot" /></button><div v-if="notificationOpen" class="notification-popover" role="dialog" aria-label="消息提醒"><header class="notification-head"><div><strong>消息提醒</strong><small>{{ unreadCount ? unreadCount + " 条未读" : "全部已读" }}</small></div><button v-if="unreadCount" type="button" class="notification-head-action interactive" @click="markAllNotificationsRead">全部已读</button></header><div class="notification-list"><button v-for="item in notifications" :key="item.id" type="button" class="notification-row interactive" :class="['notif-' + item.kind, { unread: !item.read }]" @click="openNotification(item)"><span class="notif-icon"><Check v-if="item.kind === 'success'" :size="13" /><AlertTriangle v-else-if="item.kind === 'warning'" :size="13" /><Sparkles v-else :size="13" /></span><span class="notif-body"><span class="notif-meta"><strong>{{ item.title }}</strong><em>{{ formatNotificationTime(item.createdAt) }}</em></span><small>{{ item.detail }}</small></span><i v-if="!item.read" class="notif-dot" /></button><div v-if="notifications.length === 0" class="notification-empty"><Bell :size="20" /><strong>暂无消息</strong><span>智能问数或经营诊断完成后，会在这里留下提醒。</span></div></div><footer class="notification-foot"><span>仅保留最近 30 条</span><button v-if="notifications.length > unreadCount" type="button" class="interactive" @click="clearReadNotifications">清除已读</button></footer></div></div><button class="icon-action interactive" type="button" :title="isDark ? '切换日间模式' : '切换夜间模式'" @click="toggleTheme"><Sun v-if="isDark" :size="17" /><Moon v-else :size="17" /></button><button type="button" class="primary-action interactive" @click="openUpload"><Upload :size="14" />导入数据</button></div></header>
      <div ref="pageScroll" class="page-scroll"><div class="page-content">
        <template v-if="activeSection === 'dashboard' || activeSection === 'query'">
          <section class="page-heading cockpit-heading"><div><h1 class="serif-title">{{ greeting }}，让数据 <span>回答问题</span>。</h1><p>用自然语言探索业务，让每一份洞察都有据可查。</p></div><div class="heading-actions"><button type="button" class="outline-action interactive" @click="exportDashboardCsv"><FileSpreadsheet :size="14" />导出数据</button><button type="button" class="date-range interactive" @click="notify(overview ? '当前视图基于「' + overview.datasource_name + '」实时聚合，共 ' + formatCount(overview.row_count) + ' 条真实记录' : '尚未读取到真实数据源', 'info')"><Clock3 :size="15" />{{ dateRangeLabel }}<ChevronDown :size="13" /></button></div></section>
          <section v-if="metrics.length" class="metric-grid" aria-label="核心数据指标">
            <article v-for="(metric, index) in metrics" :key="metric.key" class="metric-card interactive" :class="'metric-' + metric.tone" :style="{ '--card-index': index }"><div class="metric-top"><span>{{ metric.label }}</span><i><component :is="metricIcon(metric.key)" :size="16" /></i></div><div class="metric-value-row"><strong>{{ metric.value }}</strong><svg v-if="metric.spark.length > 1" class="mini-spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><path :d="sparkPath(metric.spark)" /></svg></div><div class="metric-foot"><span v-if="metric.change" class="metric-change" :class="metric.change_tone"><ArrowUpRight v-if="metric.change_tone !== 'down'" :size="13" /><ArrowDownRight v-else :size="13" />{{ metric.change }}</span><span>{{ metric.detail }}</span></div><i class="metric-accent" /></article>
          </section>
          <section v-else class="panel data-empty overview-empty"><Database :size="22" /><strong>{{ overviewLoading ? "正在聚合真实数据源…" : "尚未连接可分析的数据源" }}</strong><span>{{ overviewError ?? "上传真实数据并确认遮蔽字段后，这里会自动生成指标、趋势与分组洞察。" }}</span><button type="button" class="outline-action interactive" @click="openDatasources">前往数据资产</button></section>
          <section class="main-grid">
            <article class="panel trend-panel"><header class="panel-heading"><div><div class="panel-kicker"><i />数据趋势</div><h2>{{ overview?.trend?.title ?? "月度趋势" }} <span>·</span> <small>Monthly Trend</small></h2></div><div class="panel-tools"><span class="live-pill"><i />真实数据</span><button type="button" class="menu-button interactive" aria-label="趋势选项" @click="notify(overview?.trend?.subtitle ?? '当前数据源暂无月份字段', 'info')"><MoreHorizontal :size="18" /></button></div></header><div class="trend-total"><strong>{{ overview ? formatCount(overview.row_count) : "—" }}</strong><span>条记录</span><em>{{ dateRangeLabel }}</em><div v-if="trendLegendItems.length" class="trend-legend-inline"><span v-for="item in trendLegendItems" :key="item.name"><i class="legend-dot" :class="item.tone" />{{ item.name }}</span></div></div><div v-if="overview?.trend" ref="trendHost" class="trend-chart" role="img" :aria-label="overview.trend.title" /><div v-else class="trend-chart data-empty chart-empty"><span>当前数据源暂无可用的月份字段</span></div><div class="chart-foot"><span><i class="legend-dot cyan" />{{ overview?.trend?.subtitle || trendLegend }}</span><span>更新于 {{ formatTime(lastUpdated) }}</span><button type="button" @click="selectSection('reports')">查看分析 <ArrowUpRight :size="13" /></button></div></article>
            <article class="panel insight-panel"><header class="panel-heading"><div><div class="panel-kicker"><Sparkles :size="13" />数据洞察</div><h2>值得关注的信号</h2></div><button type="button" class="text-action interactive" @click="selectSection('reports')">全部洞察 <ArrowUpRight :size="13" /></button></header><div class="insight-scroll"><div class="briefing"><span class="briefing-orb"><BrainCircuit :size="19" /></span><div><small>REAL DATA BRIEFING</small><p>{{ briefingText }}</p></div></div><div class="insight-list"><button v-for="item in insightItems" :key="item.title" type="button" class="insight-row interactive" :class="'insight-' + item.kind" @click="notify(item.detail, item.kind === 'warning' ? 'warning' : 'info')"><i class="insight-symbol"><component :is="insightIcon(item.kind)" :size="15" /></i><span class="insight-body"><span class="insight-row-meta"><em>{{ item.label }}</em><small>{{ item.time }}</small></span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span><ArrowUpRight :size="14" class="insight-arrow" /></button></div></div><button type="button" class="weekly-link interactive" @click="selectSection('reports')"><span><Lightbulb :size="14" />{{ overview ? "全部指标由真实数据源即时聚合" : "等待真实数据源接入" }}</span><ArrowUpRight :size="14" /></button></article>
          </section>
          <section class="bottom-grid">
            <article class="panel channel-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">分组结构</div><h2>{{ distribution?.title ?? "字段分布" }}</h2></div><button type="button" class="menu-button interactive" @click="selectSection('reports')"><MoreHorizontal :size="18" /></button></header><div v-if="distribution" class="channel-content"><div ref="channelHost" class="channel-chart" role="img" :aria-label="distribution.title + '环图'" /><div class="channel-legend"><button v-for="item in channelLegend" :key="item.name" type="button" class="interactive" @click="notify(item.name + '占全部记录 ' + item.value, 'info')"><i :class="item.color" />{{ item.name }}<strong>{{ item.value }}</strong></button></div></div><div v-else class="data-empty channel-empty"><span>当前数据源暂无可分组字段</span></div></article>
            <article class="panel region-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">分组表现</div><h2>{{ ranking?.title ?? "分组排名" }}</h2></div><button type="button" class="range-mini interactive" @click="notify('已按' + (ranking?.metric_label ?? '占比') + '由高到低排序', 'info')">全量 <ChevronDown :size="12" /></button></header><div v-if="ranking" ref="regionHost" class="region-chart" role="img" :aria-label="ranking.title + '横向柱状图'" /><div v-else class="region-chart data-empty chart-empty"><span>当前数据源暂无可排名分组</span></div><div v-if="ranking" class="region-foot"><span><i class="legend-dot cyan" />{{ ranking.label }} · {{ ranking.metric_label }}</span><strong>{{ ranking.items[0]?.name }} {{ ranking.items[0]?.conversion_pct ?? ranking.items[0]?.share_pct }}%</strong><button type="button" @click="notify('排名由当前数据源实时聚合', 'info')">数据口径 <CircleHelp :size="12" /></button></div></article>
            <article class="panel alert-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">数据监测</div><h2>数据预警 <em v-if="alertCount" class="alert-count">{{ alertCount }}</em></h2></div><button type="button" class="text-action interactive" @click="showAlerts">查看全部 <ArrowUpRight :size="13" /></button></header><button v-for="(alert, index) in alertItems" :key="alert.title" type="button" class="alert-row interactive" :class="{ 'amber-alert': alert.level === 'info' || index > 0 }" @click="notify(alert.detail, alert.level)"><i><component :is="alertIcon(alert.level)" :size="14" /></i><span><strong>{{ alert.title }}</strong><small>{{ alert.detail }}</small></span><em>{{ alert.level === "warning" ? "关注" : "分析" }}</em></button><div v-if="alertItems.length === 0" class="alert-empty"><span>当前数据源未触发预警规则</span></div><div class="alert-foot"><span><i />聚合规则运行正常</span><small>{{ formatTime(lastUpdated) }} 更新</small></div></article>
          </section>
          <section ref="queryDock" class="query-dock" :class="{ analyzing: isAnalyzing }"><div class="query-head"><div class="query-title"><span><Sparkles :size="14" /></span><strong>问问你的数据</strong><em>AI POWERED</em></div><select v-if="readyDatasources.length > 1" v-model="preferredDatasourceId" class="query-source query-source-select" aria-label="选择分析数据源"><option v-for="item in readyDatasources" :key="item.id" :value="item.id">{{ item.name }}</option></select><button v-else type="button" class="query-source interactive" @click="openDatasources"><Database :size="13" />{{ datasourceLabel }}<ChevronDown :size="13" /></button></div><div class="query-input-row"><textarea ref="queryInput" v-model="question" rows="1" aria-label="输入数据分析问题" :placeholder="queryPlaceholder" @keydown.enter.exact.prevent="submitQuestion" /><div class="query-tools"><button type="button" class="add-question interactive" title="上传数据" @click="openUpload"><Plus :size="17" /></button><i /><button type="button" class="send-button interactive" :disabled="!question.trim() || isAnalyzing" :aria-label="isAnalyzing ? '正在分析' : '发送问题'" @click="submitQuestion"><span v-if="isAnalyzing" class="spinner" /><Send v-else :size="15" /></button></div></div><div class="query-foot"><div class="prompt-list"><span>试试</span><button v-for="prompt in prompts" :key="prompt" type="button" class="prompt-chip interactive" @click="setPrompt(prompt)">{{ prompt }}</button></div><span class="secure-note"><ShieldCheck :size="12" />只读分析 · 数据安全</span></div></section>
          <section class="answer-card"><span class="answer-glyph"><Sparkles :size="16" /></span><div class="answer-body"><div><em>{{ isAnalyzing ? "ANALYZING" : "DATA INSIGHT" }}</em><span><i />{{ analysisSource }}</span></div><p><strong>{{ latestQuestion }}</strong>{{ aiConclusion }}</p></div><button type="button" class="evidence-button interactive" @click="selectSection('reports')"><ShieldCheck :size="14" />查看证据 <span>↗</span></button></section>
          <footer class="page-footer"><span>智析 ChatBI <i>·</i> 让每个决策都有数据依据</span><span>Agent <i class="footer-agent" />{{ liveAgentReady ? "已连接" : "待配置" }} <b>·</b> {{ runs.currentRun?.status === "running" ? "分析执行中" : runs.currentRun?.status === "succeeded" ? "刚刚完成一次分析" : overview ? "真实数据已同步" : "等待数据源" }}</span></footer>
        </template>

        <template v-else-if="activeSection === 'reports'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />REAL DATA · EVIDENCE READY</div><h1 class="serif-title">洞察报告 <span>一目了然</span>。</h1><p>每份分析都包含清晰口径、证据引用和可追溯的运行记录。</p></div><div class="heading-actions"><button class="outline-action interactive" type="button" @click="exportReportCsv"><FileSpreadsheet :size="14" />导出数据 CSV</button><button class="primary-action interactive" type="button" @click="downloadReport"><Download :size="14" />导出最新报告</button></div></section>
          <section class="panel report-hero"><div class="report-copy"><span class="report-label"><Sparkles :size="13" />真实数据简报 · {{ overview?.period_label ?? "等待数据源" }}</span><h2>{{ latestQuestion }}</h2><p>{{ aiConclusion }}</p><div class="report-meta"><span><Database :size="13" />{{ analysisSource }}</span><span><ShieldCheck :size="13" />指标由真实数据源即时聚合</span></div><button type="button" class="primary-action interactive" @click="downloadReport"><FileText :size="14" />导出完整报告</button></div><div class="report-art"><div class="report-chart-head"><span><BarChart3 :size="13" />分析图表</span><em>{{ reportChartImage ? reportChartNote : (reportChartPayload?.summary ?? "真实查询结果") }}</em></div><img v-if="reportChartImage" :src="reportChartImage" class="report-chart-image" alt="分析图表" /><div v-else-if="reportChartPayload" ref="reportChartHost" class="report-chart" role="img" :aria-label="reportChartPayload.summary" /><div v-else class="report-chart-empty"><BarChart3 :size="18" /><span>{{ reportChartLoading ? "正在从查询产物生成图表…" : reportChartNote }}</span></div><div class="report-chart-foot"><span>{{ reportChartImage ? reportChartNote : (reportChartPayload?.note ?? "图表由本次受控 SQL 查询结果生成") }}</span><button v-if="reportRun" type="button" class="interactive" @click="selectSection('query')">继续分析 <ArrowUpRight :size="12" /></button></div></div></section>
          <section class="panel followup-panel"><header class="panel-heading"><div><div class="panel-kicker">CONTEXT FOLLOW-UP</div><h2>继续追问这份报告</h2></div><span class="followup-context"><MessageSquareText :size="12" />{{ followupContext }}</span></header><div ref="followupThread" class="followup-thread"><div v-for="message in followupMessages" :key="message.id" class="followup-item" :class="message.role"><small>{{ message.role === "user" ? "你" : "智析" }}</small><div class="followup-body"><p>{{ message.content_text }}</p><AskAnswerChart v-if="message.id === followupChartMessageId && message.run_id" :run-id="message.run_id" @rendered="scrollFollowupToEnd" /></div></div><div v-if="followupPending" class="followup-item user"><small>你</small><p>{{ pendingFollowupQuestion }}</p></div><div v-if="followupPending" class="followup-item assistant pending"><small>智析</small><p>正在沿用当前会话上下文继续查询真实数据…</p></div><div v-if="followupError" class="followup-item assistant error"><small>智析</small><p>{{ followupError }}</p></div><div v-if="!followupMessages.length && !followupPending && !followupError" class="followup-empty"><span>在上方智能问数中完成一次分析后，就可以在这里基于报告继续追问。</span></div></div><div class="followup-input-row"><textarea ref="followupInput" v-model="followupQuestion" rows="1" placeholder="基于当前报告继续追问，例如：按流量类型拆分呢？" @keydown.enter.exact.prevent="askFollowUp" /><button type="button" class="send-button interactive" :disabled="!followupQuestion.trim() || followupPending || !followupReady" :aria-label="followupPending ? '追问分析中' : '发送追问'" @click="askFollowUp"><span v-if="followupPending" class="spinner" /><Send v-else :size="15" /></button></div><div class="followup-foot"><span>追问会沿用当前会话与数据源</span><span>{{ followupReady ? "Agent 已就绪" : "请先在智能问数中完成一次分析" }}</span></div></section>
          <section class="panel table-panel"><header class="panel-heading"><div><div class="panel-kicker">ANALYSIS HISTORY</div><h2>最近的分析会话</h2></div><button type="button" class="outline-action interactive" @click="sessions.load()"><RefreshCw :size="14" />刷新</button></header><div v-if="reportRows.length" class="data-table"><div class="table-row table-head"><span>报告名称</span><span>数据源</span><span>生成时间</span><span>状态</span><span /></div><button v-for="row in reportRows" :key="row.id" type="button" class="table-row interactive" @click="openReport(row.id)"><span class="report-name"><i><FileText :size="15" /></i><strong>{{ row.title }}</strong></span><span>{{ row.type }}</span><span>{{ row.time }}</span><span class="success-state"><Check :size="13" />可回放</span><ArrowUpRight :size="15" /></button></div><div v-else class="data-empty table-empty"><FileText :size="20" /><strong>暂无真实分析报告</strong><span>在智能问数中发起一次真实分析后，会话与证据链会自动出现在这里。</span><button type="button" class="outline-action interactive" @click="selectSection('query')">去提问</button></div></section>
        </template>

        <template v-else-if="activeSection === 'diagnosis'">
          <section class="page-heading module-heading diagnosis-heading">
            <div>
              <div class="eyebrow"><i />经营诊断 · 结论可复核</div>
              <h1>经营诊断 <span>先看结论，再看原因。</span></h1>
              <p>可以直接用一句话提问，也可以手动选择指标和分组；结论和计算细节都可复核。</p>
            </div>
            <div class="heading-actions">
              <button class="outline-action interactive" type="button" :disabled="!diagnosisResult" @click="exportDiagnosisCsv">
                <FileSpreadsheet :size="14" />导出数据 CSV
              </button>
              <button class="primary-action interactive" type="button" :disabled="!diagnosisResult" @click="downloadDiagnosisReport">
                <Download :size="14" />导出诊断报告
              </button>
            </div>
          </section>

          <section class="panel diagnosis-ask">
            <div class="diagnosis-ask-head">
              <span class="diagnosis-ask-icon"><Sparkles :size="15" /></span>
              <div>
                <strong>用一句话问诊断</strong>
                <small>AI 解析问题后自动选好指标、分组和时间，也可以手动修改</small>
              </div>
              <em>{{ diagnosisIntent ? (diagnosisIntent.source === "model" ? "AI 解析" : "规则识别") : "自然语言" }}</em>
            </div>
            <form class="diagnosis-ask-form" @submit.prevent="askDiagnosis">
              <input v-model="diagnosisQuestion" :placeholder="diagnosisAskPlaceholder" :disabled="diagnosisAsking" aria-label="用一句话问经营诊断" />
              <button type="submit" class="primary-action interactive" :disabled="diagnosisAsking || !diagnosisQuestion.trim() || !diagnosisReady">
                <span v-if="diagnosisAsking" class="spinner" /><Send v-else :size="14" />{{ diagnosisAsking ? "解析中" : "问诊断" }}
              </button>
            </form>
            <div v-if="diagnosisIntent" class="diagnosis-ask-understood" :class="{ failed: !diagnosisIntent.understood }">
              <span class="intent-tag">{{ diagnosisIntent.understood ? "已理解" : "需补充" }}</span>
              <span>{{ diagnosisIntent.explanation }}</span>
              <em v-if="diagnosisIntent.confidence > 0">置信 {{ Math.round(diagnosisIntent.confidence * 100) }}%</em>
            </div>
            <div v-if="diagnosisSuggestions.length" class="diagnosis-ask-suggestions">
              <span>试试</span>
              <button v-for="text in diagnosisSuggestions" :key="text" type="button" class="interactive" @click="applyDiagnosisQuestion(text)">{{ text }}</button>
            </div>
          </section>

          <section class="panel diagnosis-config">
            <header class="panel-heading">
              <div><div class="panel-kicker"><Stethoscope :size="13" />DIAGNOSIS SETTINGS</div><h2>分析设置</h2></div>
              <div class="diagnosis-config-actions">
                <select v-if="readyDatasources.length > 1" v-model="preferredDatasourceId" class="diagnosis-select" aria-label="选择诊断数据源">
                  <option v-for="item in readyDatasources" :key="item.id" :value="item.id">{{ item.name }}</option>
                </select>
                <button type="button" class="outline-action interactive" :disabled="diagnosisCapabilitiesLoading" @click="loadDiagnosis(true)">
                  <RefreshCw :size="14" />{{ diagnosisCapabilitiesLoading ? "识别中" : "重新识别字段" }}
                </button>
              </div>
            </header>
            <div class="diagnosis-controls">
              <label class="diagnosis-field">
                <span>看哪个指标（合计）</span>
                <select v-model="diagnosisMetric" :disabled="!diagnosisReady || diagnosisRunning" @change="clearDiagnosisIntent">
                  <option v-for="item in diagnosisCapabilities?.measures ?? []" :key="item.name" :value="item.name">{{ item.label }}</option>
                </select>
              </label>
              <label class="diagnosis-field">
                <span>按什么分组对比</span>
                <select v-model="diagnosisDimension" :disabled="!diagnosisReady || diagnosisRunning" @change="clearDiagnosisIntent">
                  <option v-for="item in diagnosisCapabilities?.dimensions ?? []" :key="item.name" :value="item.name">{{ item.label }}</option>
                </select>
              </label>
              <label class="diagnosis-field">
                <span>按哪个时间字段（按月）</span>
                <select v-model="diagnosisTime" :disabled="!diagnosisReady || diagnosisRunning" @change="clearDiagnosisIntent">
                  <option v-for="item in diagnosisCapabilities?.time_columns ?? []" :key="item.name" :value="item.name">{{ item.label }}</option>
                </select>
              </label>
              <label class="diagnosis-field narrow">
                <span>展示几个原因</span>
                <select v-model.number="diagnosisTopN" :disabled="!diagnosisReady || diagnosisRunning">
                  <option :value="4">4</option>
                  <option :value="6">6</option>
                  <option :value="8">8</option>
                </select>
              </label>
              <button type="button" class="primary-action diagnosis-run interactive" :disabled="!diagnosisReady || diagnosisRunning" @click="executeDiagnosis">
                <span v-if="diagnosisRunning" class="spinner" /><Activity v-else :size="14" />{{ diagnosisRunning ? "诊断中" : "开始诊断" }}
              </button>
            </div>
            <div class="diagnosis-pillars">
              <span><i>01</i>看清增减来源</span>
              <span><i>02</i>给出可能原因</span>
              <span><i>03</i>标注可信程度</span>
              <span><i>04</i>数据可以复核</span>
              <em v-if="diagnosisCapabilities">{{ formatCount(diagnosisCapabilities.row_count) }} 条记录 · {{ diagnosisCapabilities.table }}</em>
              <em v-else>等待数据源</em>
            </div>
          </section>

          <section v-if="!diagnosisReady" class="panel data-empty diagnosis-empty">
            <Stethoscope :size="24" />
            <strong>{{ diagnosisCapabilitiesLoading ? "正在识别可诊断字段…" : "当前数据源暂不可诊断" }}</strong>
            <span>{{ diagnosisError ?? diagnosisCapabilities?.message ?? "请先在数据资产中接入真实数据源并确认遮蔽字段。" }}</span>
            <button type="button" class="outline-action interactive" @click="openDatasources">查看数据资产</button>
          </section>

          <template v-else>
            <template v-if="diagnosisResult">
              <section class="panel diagnosis-headline">
                <div class="diagnosis-headline-copy">
                  <small>一句话结论</small>
                  <p>{{ diagnosisHeadline }}</p>
                  <div class="diagnosis-headline-tags">
                    <span v-if="diagnosisDrivers.drag" class="diagnosis-driver down">主要拖累 · {{ diagnosisDrivers.drag.group }} {{ formatSigned(diagnosisDrivers.drag.delta) }}</span>
                    <span v-if="diagnosisDrivers.lift" class="diagnosis-driver up">主要拉动 · {{ diagnosisDrivers.lift.group }} {{ formatSigned(diagnosisDrivers.lift.delta) }}</span>
                  </div>
                </div>
                <div class="diagnosis-headline-side" :class="'verify-' + diagnosisResult.verification.status">
                  <span>结论核对</span>
                  <strong>{{ diagnosisResult.verification.passed }}/{{ diagnosisResult.verification.total }}</strong>
                  <small>{{ diagnosisVerificationText }}</small>
                </div>
              </section>

              <section class="diagnosis-kpis">
                <article class="panel diagnosis-kpi">
                  <span>本期 {{ diagnosisResult.period.current_label }} · {{ diagnosisResult.metric_label }}</span>
                  <strong>{{ formatMetric(diagnosisResult.period.current_total) }}</strong>
                  <small>{{ formatCount(diagnosisResult.period.current_rows) }} 条记录</small>
                </article>
                <article class="panel diagnosis-kpi">
                  <span>上期 {{ diagnosisResult.period.baseline_label }}</span>
                  <strong>{{ formatMetric(diagnosisResult.period.baseline_total) }}</strong>
                  <small>{{ formatCount(diagnosisResult.period.baseline_rows) }} 条记录</small>
                </article>
                <article class="panel diagnosis-kpi" :class="{ 'kpi-down': diagnosisResult.period.delta < 0 }">
                  <span>净变化</span>
                  <strong>{{ diagnosisResult.period.delta >= 0 ? "+" : "" }}{{ formatMetric(diagnosisResult.period.delta) }}</strong>
                  <small>{{ diagnosisResult.period.delta_pct === null ? "上期为零，无法计算百分比" : (diagnosisResult.period.delta_pct >= 0 ? "+" : "") + diagnosisResult.period.delta_pct.toFixed(2) + "%" }}</small>
                </article>
                <article class="panel diagnosis-kpi" :class="'verify-' + diagnosisResult.verification.status">
                  <span>结论核对</span>
                  <strong>{{ diagnosisResult.verification.passed }}/{{ diagnosisResult.verification.total }}</strong>
                  <small>{{ diagnosisVerificationText }}</small>
                </article>
              </section>

              <section class="diagnosis-grid">
                <article class="panel diagnosis-chart-panel">
                  <header class="panel-heading">
                    <div><div class="panel-kicker">WHERE THE CHANGE CAME FROM</div><h2>谁在拉动，谁在拖累</h2></div>
                    <span class="diagnosis-tag">按{{ diagnosisResult.dimension_label }} · 前 {{ diagnosisResult.contributions.length }} 项</span>
                  </header>
                  <div ref="diagnosisHost" class="diagnosis-chart" role="img" aria-label="各分组拉动与拖累金额" />
                  <div class="chart-foot">
                    <span>{{ diagnosisResult.chart.baseline_label }} → {{ diagnosisResult.chart.current_label }}</span>
                    <span>各项有增有减，单项占比可能超过 100%</span>
                  </div>
                </article>
                <article class="panel diagnosis-hypotheses">
                  <header class="panel-heading">
                    <div><div class="panel-kicker">POSSIBLE REASONS</div><h2>可能原因</h2></div>
                    <span class="diagnosis-tag">{{ diagnosisResult.hypotheses.length }} 条 · 按可信度排序</span>
                  </header>
                  <div v-for="(hypothesis, index) in diagnosisResult.hypotheses" :key="hypothesis.id" class="diagnosis-hypothesis" :class="'hyp-' + hypothesis.status">
                    <div class="hyp-head">
                      <strong>原因 {{ index + 1 }} · {{ diagnosisStatusLabel(hypothesis.status) }}</strong>
                      <em>{{ Math.round(hypothesis.score * 100) }}<small> 分</small></em>
                    </div>
                    <p>{{ hypothesisPlainText(hypothesis) }}</p>
                    <div class="hyp-meter"><i :style="{ width: Math.round(hypothesis.score * 100) + '%' }" /></div>
                    <div class="hyp-evidence">{{ hypothesisEvidenceSummary(hypothesis) }}</div>
                  </div>
                </article>
              </section>

              <section class="panel diagnosis-checks">
                <header class="panel-heading">
                  <div><div class="panel-kicker">CONSISTENCY CHECKS</div><h2>结论核对</h2></div>
                  <span class="diagnosis-tag" :class="'verify-' + diagnosisResult.verification.status">{{ diagnosisStatusLabel(diagnosisResult.verification.status) }}</span>
                </header>
                <div class="diagnosis-check-grid">
                  <div v-for="check in diagnosisResult.verification.checks" :key="check.name" class="diagnosis-check" :class="{ failed: !check.passed }">
                    <i><Check v-if="check.passed" :size="13" /><AlertTriangle v-else :size="13" /></i>
                    <div><strong>{{ diagnosisCheckLabel(check.name) }}</strong><small>{{ check.passed ? "通过" : "未通过" }}</small></div>
                  </div>
                </div>
                <p class="diagnosis-note">核对只确认分项与整体能对上、数据足够完整，不代表因果关系。</p>
              </section>

              <section class="diagnosis-technical">
                <button type="button" class="diagnosis-technical-toggle interactive" @click="diagnosisTechnicalOpen = !diagnosisTechnicalOpen">
                  <span><Settings2 :size="14" />查看计算口径与验证细节</span>
                  <ChevronDown :size="15" :class="{ open: diagnosisTechnicalOpen }" />
                </button>
                <div v-if="diagnosisTechnicalOpen" class="diagnosis-technical-body">
                  <div class="diagnosis-tech-grid">
                    <article class="panel diagnosis-tech-card">
                      <strong>引擎能力</strong>
                      <ul>
                        <li>确定性配方编译（结果可复现）</li>
                        <li>贡献分解算子</li>
                        <li>假设-证据图</li>
                        <li>不变量验证</li>
                      </ul>
                    </article>
                    <article class="panel diagnosis-tech-card">
                      <strong>配方信息</strong>
                      <div class="tech-line"><span>配方编号</span><code>{{ diagnosisResult.recipe_id }}</code></div>
                      <div class="tech-line"><span>配方哈希</span><code>{{ diagnosisResult.recipe_hash.slice(0, 24) }}…</code></div>
                      <div class="tech-line"><span>引擎 / 数据结构</span><em>{{ diagnosisResult.engine_version }} · v{{ diagnosisResult.schema_revision }}</em></div>
                      <div class="tech-line"><span>耗时 / 生成时间</span><em>{{ diagnosisResult.duration_ms }} ms · {{ diagnosisResult.generated_at }}</em></div>
                    </article>
                  </div>

                  <article class="panel diagnosis-tech-card">
                    <strong>引擎原始叙述</strong>
                    <div class="diagnosis-narrative-body">
                      <template v-for="(block, index) in diagnosisNarrativeBlocks" :key="index">
                        <h3 v-if="block.type === 'heading'">{{ block.text }}</h3>
                        <p v-else-if="block.type === 'item'" class="narrative-item">{{ block.text }}</p>
                        <p v-else>{{ block.text }}</p>
                      </template>
                    </div>
                  </article>

                  <article class="panel diagnosis-evidence">
                    <header class="panel-heading"><div><div class="panel-kicker">EVIDENCE LEDGER</div><h2>证据清单</h2></div><span class="diagnosis-tag">{{ diagnosisResult.evidence.length }} 项 · 缺失率 {{ (diagnosisResult.quality.missing_rate * 100).toFixed(2) }}%</span></header>
                    <div class="evidence-table">
                      <div class="evidence-row evidence-head"><span>ID</span><span>分组</span><span>证据</span><span>方法</span><span>样本</span><span>置信</span></div>
                      <div v-for="item in diagnosisResult.evidence" :key="item.id" class="evidence-row" :class="'evidence-' + item.status">
                        <span class="evidence-id">{{ item.id }}</span>
                        <span>{{ item.group }}</span>
                        <span>{{ item.claim }}</span>
                        <span :title="item.method">{{ diagnosisMethodLabel(item.method) }}</span>
                        <span>{{ formatCount(item.sample_size) }}</span>
                        <span>{{ Math.round(item.confidence_level * 100) }}%</span>
                      </div>
                    </div>
                  </article>

                  <article class="panel diagnosis-tech-card">
                    <strong>验证明细</strong>
                    <div v-for="check in diagnosisResult.verification.checks" :key="check.name" class="verify-row" :class="{ failed: !check.passed }">
                      <i><Check v-if="check.passed" :size="12" /><AlertTriangle v-else :size="12" /></i>
                      <div><strong>{{ check.label }}</strong><small>{{ check.detail }}</small></div>
                      <em>{{ Math.round(check.confidence_level * 100) }}%</em>
                    </div>
                    <div class="verify-caveats"><span v-for="caveat in diagnosisResult.verification.caveats" :key="caveat">{{ caveat }}</span></div>
                  </article>
                </div>
              </section>
            </template>

            <section v-else class="panel data-empty diagnosis-empty">
              <Stethoscope :size="24" />
              <strong>{{ diagnosisRunning ? "正在执行诊断…" : "数据检查完成" }}</strong>
              <span>{{ diagnosisError ?? diagnosisCapabilities?.message }}</span>
              <button type="button" class="outline-action interactive" :disabled="diagnosisRunning" @click="executeDiagnosis">开始诊断</button>
            </section>
          </template>
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
