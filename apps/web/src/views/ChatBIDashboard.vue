<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import type { ECharts, EChartsOption } from "echarts";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, BrainCircuit,
  Check, ChevronDown, CircleHelp, Clock3, Database, Download, FileText, Layers,
  LayoutDashboard, Lightbulb, MessageSquareText, MoreHorizontal, Plus, RefreshCw,
  Send, ShieldCheck, Sparkles, TrendingUp, Upload, Wallet,
} from "@lucide/vue";
import { useRouter } from "vue-router";
import { buildApiUrl } from "@/api/client";
import demoSummary from "../data/demoSummary.json";
import type { Message } from "@/api/types";
import { useDatasourceStore } from "@/stores/datasourceStore";
import { useModelStore } from "@/stores/modelStore";
import { useRunStore } from "@/stores/runStore";
import { useSessionStore } from "@/stores/sessionStore";

type Section = "dashboard" | "query" | "reports" | "ledger" | "finance";
type ToastKind = "success" | "info" | "warning";
function formatWan(amount: number): string {
  return "¥" + (amount / 10000).toFixed(1) + "万";
}
const latestDemoMonth = demoSummary.latest_month;
const leadingDemoRegion = latestDemoMonth.regions[0]!;
const leadingDemoChannel = latestDemoMonth.channels[0]!;
const initialConclusion =
  "截至 2026 年 10 月 " + latestDemoMonth.as_of_day + " 日，订单金额为 " +
  formatWan(latestDemoMonth.revenue) + "，较 9 月同期" +
  (latestDemoMonth.growth_pct >= 0 ? "增长 " : "下降 ") +
  Math.abs(latestDemoMonth.growth_pct).toFixed(1) + "%；当期毛利率为 " +
  latestDemoMonth.gross_margin_pct.toFixed(1) + "%。";
const router = useRouter();
const datasources = useDatasourceStore();
const models = useModelStore();
const sessions = useSessionStore();
const runs = useRunStore();
const activeSection = ref<Section>("dashboard");
const question = ref("");
const isAnalyzing = ref(false);
const queryInput = ref<HTMLTextAreaElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const toast = ref<{ message: string; kind: ToastKind } | null>(null);
const latestQuestion = ref("本月订单金额和毛利率表现如何？");
const aiConclusion = ref(initialConclusion);
const analysisSource = ref("演示数据 · " + demoSummary.totals.order_count + " 笔订单 · 更新至 " + demoSummary.period.end);
const lastUpdated = ref(new Date());
const trendHost = ref<HTMLElement | null>(null);
const channelHost = ref<HTMLElement | null>(null);
const regionHost = ref<HTMLElement | null>(null);
let trendChart: ECharts | null = null;
let channelChart: ECharts | null = null;
let regionChart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;
let toastTimer: number | null = null;

const navItems = [
  { id: "dashboard" as const, label: "经营驾驶舱", icon: LayoutDashboard },
  { id: "query" as const, label: "智能问数", icon: MessageSquareText },
  { id: "reports" as const, label: "洞察报告", icon: FileText },
  { id: "ledger" as const, label: "项目台账", icon: Layers },
  { id: "finance" as const, label: "收支管理", icon: Wallet },
];
const prompts = [
  "对比本月与上月各区域销售额",
  "今年各产品线的收入趋势如何？",
  "分析本月活跃客户数与平均订单金额",
];
const reportRows = [
  { title: "Q3 经营复盘与增长洞察", type: "季度分析", time: "今天 09:42" },
  { title: "华东区域销售趋势分析", type: "区域分析", time: "昨天 16:18" },
  { title: "产品线毛利率异常追踪", type: "风险诊断", time: "10 月 27 日" },
];
const ledgerRows = [
  { name: "数据资产接入与治理", owner: "数据运营组", progress: 82, stage: "联调验收", date: "2026-11-05", color: "cyan" },
  { name: "智能经营分析一期", owner: "业务中台", progress: 64, stage: "功能开发", date: "2026-11-12", color: "violet" },
  { name: "销售预测模型优化", owner: "商业分析部", progress: 37, stage: "方案设计", date: "2026-11-19", color: "amber" },
  { name: "财务报表自动化", owner: "财务共享中心", progress: 18, stage: "需求梳理", date: "2026-11-28", color: "blue" },
];
const financeRows = [
  ...demoSummary.recent_transactions.slice(0, 4).map((row) => ({
    name: row.customer + " · " + row.region,
    category: row.channel,
    date: row.date.slice(5) + " " + row.time,
    amount: row.amount,
    state: row.payment_status,
    positive: row.payment_status === "已回款",
  })),
];
const insightItems = ref([
  { kind: "positive", label: "区域领跑", title: leadingDemoRegion.name + "贡献 " + leadingDemoRegion.share_pct.toFixed(1) + "%", detail: "10 月截至 29 日，该区域订单金额 " + formatWan(leadingDemoRegion.revenue) + "。", icon: TrendingUp, time: "10/29" },
  { kind: "warning", label: "待回款", title: demoSummary.totals.unpaid_order_count + " 笔订单待回款", detail: "应收金额 " + formatWan(demoSummary.totals.open_receivables) + "，可按区域及客户分组核对。", icon: AlertTriangle, time: "10/29" },
  { kind: "neutral", label: "数据范围", title: demoSummary.totals.customer_count + " 家客户 · 906 笔订单", detail: "数据覆盖 2026 年 1 月至 10 月 29 日，累计毛利率 " + demoSummary.totals.gross_margin_pct.toFixed(1) + "%。", icon: ShieldCheck, time: "10/29" },
]);
const datasourceReady = computed(() => datasources.items.find((item) =>
  (item.status === "ready" || item.status === "schema_ready") && item.mask_fields_confirmed,
) ?? null);
const activeModel = computed(() => models.items.find((item) => item.is_active) ?? null);
const liveAgentReady = computed(() => datasourceReady.value !== null && activeModel.value !== null);
const datasourceLabel = computed(() => datasourceReady.value?.name ?? "演示 · 906 条订单");
const activeTitle = computed(() => ({
  dashboard: "经营驾驶舱",
  query: "智能问数",
  reports: "洞察报告",
  ledger: "项目流程台账",
  finance: "收支管理",
}[activeSection.value]));
const greeting = computed(() => {
  const hour = lastUpdated.value.getHours();
  return hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";
});
const metrics = computed(() => [
  { label: "10 月营收 · 截至 29 日", value: formatWan(latestDemoMonth.revenue), change: (latestDemoMonth.growth_pct >= 0 ? "+" : "") + latestDemoMonth.growth_pct.toFixed(1) + "%", icon: Wallet, color: "cyan", foot: "较 9 月同期", spark: "M2 24 C12 21 16 25 25 20 S40 17 49 12 S65 18 74 10 S88 9 98 2" },
  { label: "活跃客户", value: latestDemoMonth.active_customers.toLocaleString(), change: demoSummary.totals.customer_count + " 家累计", icon: Layers, color: "violet", foot: "10/01—10/29", spark: "M2 22 C12 24 16 16 25 19 S42 11 51 14 S65 5 76 9 S90 4 98 2" },
  { label: "平均订单金额", value: "¥" + latestDemoMonth.avg_order_value.toLocaleString("zh-CN", { maximumFractionDigits: 0 }), change: latestDemoMonth.order_count + " 笔订单", icon: BarChart3, color: "blue", foot: "10 月月均", spark: "M2 20 C10 17 17 21 27 15 S40 17 49 11 S62 12 70 8 S88 7 98 2" },
  { label: "累计毛利率", value: demoSummary.totals.gross_margin_pct.toFixed(1) + "%", change: formatWan(demoSummary.totals.gross_profit), icon: ShieldCheck, color: "green", foot: "2026 年累计", spark: "M2 20 C14 19 18 14 27 15 S41 9 51 10 S68 4 77 7 S89 4 98 2" },
]);
const channelLegend = computed(() => latestDemoMonth.channels.map((item, index) => ({
  name: item.name,
  value: item.share_pct.toFixed(1) + "%",
  color: ["cyan", "blue", "violet", "green"][index] ?? "cyan",
})));

function notify(message: string, kind: ToastKind = "success") {
  toast.value = { message, kind };
  if (toastTimer !== null) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.value = null; }, 2800);
}
function selectSection(section: Section) {
  activeSection.value = section;
  if (section === "query") void nextTick(() => queryInput.value?.focus());
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
function makeIdempotencyKey() {
  const id = globalThis.crypto?.randomUUID?.();
  return id ? "chatbi-" + id : "chatbi-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
}
function refreshDashboard() {
  lastUpdated.value = new Date();
  updateCharts();
  notify("演示数据已重新载入");
}
function updateCharts() {
  const monthLabels = demoSummary.months.map((item) => item.month.slice(5) + "月");
  const revenue = demoSummary.months.map((item) => +(item.revenue / 10000).toFixed(1));
  const grossProfit = demoSummary.months.map((item) => +(item.gross_profit / 10000).toFixed(1));
  trendChart?.setOption({
    xAxis: { data: monthLabels },
    series: [{ data: revenue }, { data: grossProfit }],
  }, { lazyUpdate: true });
  channelChart?.setOption({
    series: [{ data: demoSummary.channels.map((item) => ({ name: item.name, value: item.revenue })) }],
    graphic: [{ type: "text", left: "center", top: "40%", style: { text: formatWan(latestDemoMonth.revenue), fill: "#e6f6ff", fontSize: 16, fontWeight: 700, fontFamily: "Inter,sans-serif" } }],
  }, { lazyUpdate: true });
  regionChart?.setOption({
    yAxis: { data: latestDemoMonth.regions.map((item) => item.name) },
    series: [{ data: latestDemoMonth.regions.map((item) => +(item.revenue / 10000).toFixed(1)) }],
  }, { lazyUpdate: true });
}
function initCharts() {
  resizeObserver?.disconnect();
  trendChart?.dispose(); channelChart?.dispose(); regionChart?.dispose();
  trendChart = null; channelChart = null; regionChart = null;
  if (trendHost.value) {
    trendChart = echarts.init(trendHost.value);
    trendChart.setOption({
      animationDuration: 1100, animationEasing: "elasticOut",
      grid: { left: 5, right: 12, top: 25, bottom: 26, containLabel: true },
      legend: { top: 0, right: 4, itemWidth: 8, itemHeight: 8, textStyle: { color: "#8091ad", fontSize: 10 }, data: ["月度营收", "月度毛利"] },
      tooltip: { trigger: "axis", backgroundColor: "rgba(8,19,39,.96)", borderColor: "rgba(77,190,255,.25)", textStyle: { color: "#e6f4ff", fontSize: 11 }, valueFormatter: (value) => "¥" + Number(value).toLocaleString() + " 万" },
      xAxis: { type: "category", boundaryGap: false, data: demoSummary.months.map((item) => item.month.slice(5) + "月"), axisLine: { lineStyle: { color: "rgba(120,165,206,.18)" } }, axisTick: { show: false }, axisLabel: { color: "#7486a1", fontSize: 10, margin: 12 } },
      yAxis: { type: "value", min: 0, max: 100, splitNumber: 4, axisLabel: { color: "#6f829d", fontSize: 10, formatter: "{value}万" }, splitLine: { lineStyle: { color: "rgba(104,153,199,.1)", type: "dashed" } }, axisLine: { show: false } },
      series: [
        { name: "月度营收", type: "line", smooth: 0.42, symbol: "circle", symbolSize: 5, data: demoSummary.months.map((item) => +(item.revenue / 10000).toFixed(1)), lineStyle: { width: 3, color: "#53d6ff", shadowColor: "rgba(48,194,255,.4)", shadowBlur: 12 }, itemStyle: { color: "#6ce6ff", borderColor: "#071a30", borderWidth: 2 }, areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"rgba(45,186,255,.28)"},{offset:1,color:"rgba(45,186,255,.01)"}]) }, emphasis: { focus: "series", scale: 1.5 } },
        { name: "月度毛利", type: "line", smooth: 0.45, symbol: "none", data: demoSummary.months.map((item) => +(item.gross_profit / 10000).toFixed(1)), lineStyle: { width: 2, type: "dashed", color: "#8978ff" } },
      ],
    } as EChartsOption);
  }
  if (channelHost.value) {
    channelChart = echarts.init(channelHost.value);
    channelChart.setOption({
      animationDuration: 1100, animationEasing: "elasticOut",
      tooltip: { trigger: "item", backgroundColor: "rgba(8,19,39,.96)", borderColor: "rgba(77,190,255,.25)", textStyle: { color: "#e6f4ff", fontSize: 11 }, formatter: "{b} · {d}%" },
      color: ["#43d7f5", "#6889ff", "#9b7aff", "#39cda7"],
      series: [{ type: "pie", radius: ["63%","84%"], center: ["50%","50%"], label: { show: false }, labelLine: { show: false }, itemStyle: { borderColor: "#0a1730", borderWidth: 3, borderRadius: 5 }, emphasis: { scale: true, scaleSize: 7 }, data: demoSummary.latest_month.channels.map((item) => ({ value: item.revenue, name: item.name })) }],
      graphic: [{ type:"text", left:"center", top:"40%", style:{ text:formatWan(latestDemoMonth.revenue), fill:"#e6f6ff", fontSize:16, fontWeight:700, fontFamily:"Inter,sans-serif" } }, { type:"text", left:"center", top:"57%", style:{ text:"10月截至29日", fill:"#7f94b2", fontSize:9, fontFamily:"Inter,sans-serif" } }],
    } as EChartsOption);
  }
  if (regionHost.value) {
    regionChart = echarts.init(regionHost.value);
    regionChart.setOption({
      animationDuration: 1000, animationEasing: "elasticOut",
      grid: { left: 2, right: 22, top: 7, bottom: 4, containLabel: true },
      tooltip: { trigger:"axis", axisPointer:{type:"shadow"}, backgroundColor:"rgba(8,19,39,.96)", borderColor:"rgba(77,190,255,.25)", textStyle:{color:"#e6f4ff",fontSize:11}, valueFormatter:(value)=>"¥"+value+" 万" },
      xAxis: { type:"value", max:35, show:false },
      yAxis: { type:"category", inverse:true, data:latestDemoMonth.regions.map((item) => item.name), axisTick:{show:false}, axisLine:{show:false}, axisLabel:{color:"#9cb0c9",fontSize:11,margin:12} },
      series: [{ type:"bar", data:latestDemoMonth.regions.map((item) => +(item.revenue/10000).toFixed(1)), barWidth:10, showBackground:true, backgroundStyle:{color:"rgba(81,129,184,.09)",borderRadius:99}, itemStyle:{borderRadius:99,color:new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:"#38bdf8"},{offset:1,color:"#8b7bff"}])}, label:{show:true,position:"right",color:"#92a9c5",fontSize:10,formatter:"{c}万"} }],
    } as EChartsOption);
  }
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => { trendChart?.resize(); channelChart?.resize(); regionChart?.resize(); });
    [trendHost.value, channelHost.value, regionHost.value].forEach((host) => { if (host) resizeObserver?.observe(host); });
  }
}
function setPrompt(prompt: string) {
  question.value = prompt;
  selectSection("query");
}
function demoAnswer(prompt: string) {
  const lower = prompt.toLowerCase();
  const month = demoSummary.latest_month;
  const topRegion = month.regions[0]!;
  const topChannel = month.channels[0]!;
  const growthWord = month.growth_pct >= 0 ? "增长 " : "下降 ";
  if (lower.includes("毛利") || lower.includes("利润")) {
    const profitChange = month.gross_profit_change_pct ?? 0;
    aiConclusion.value = "截至 10 月 29 日，10 月同期毛利 " + formatWan(month.gross_profit) +
      "，毛利率 " + month.gross_margin_pct.toFixed(1) + "%；较 9 月同期毛利" +
      (profitChange >= 0 ? "增长 " : "下降 ") +
      Math.abs(profitChange).toFixed(1) + "%。";
  } else if (lower.includes("转化率") || lower.includes("线索")) {
    aiConclusion.value = "这份演示订单表记录了 " + month.active_customers +
      " 家本月有下单客户和 " + month.order_count +
      " 笔订单，但没有线索或销售漏斗阶段字段，因此不能据此计算客户转化率。";
  } else if (lower.includes("客户") || lower.includes("留存")) {
    aiConclusion.value = "截至 10 月 29 日，有下单客户 " + month.active_customers +
      " 家、订单 " + month.order_count + " 笔，平均订单金额 ¥" +
      month.avg_order_value.toLocaleString("zh-CN", { maximumFractionDigits: 0 }) +
      "。演示表没有流失标记或客户生命周期阶段，留存率需要补充对应数据后再算。";
  } else if (lower.includes("渠道")) {
    aiConclusion.value = "10 月截至 29 日，" + topChannel.name + "贡献最高，占本月订单金额 " +
      topChannel.share_pct.toFixed(1) + "%（" + formatWan(topChannel.revenue) +
      "）。其余渠道占比可在收入来源分布图中查看。";
  } else if (lower.includes("区域") || lower.includes("地区")) {
    aiConclusion.value = "10 月截至 29 日，" + topRegion.name + "区域排名第一，占本月订单金额 " +
      topRegion.share_pct.toFixed(1) + "%（" + formatWan(topRegion.revenue) +
      "）；当前区域排名基于演示订单金额汇总。";
  } else if (lower.includes("产品") || lower.includes("品类")) {
    const topProduct = demoSummary.products[0]!;
    aiConclusion.value = "2026 年 1 月至 10 月 29 日，" + topProduct.name +
      "累计订单金额最高，为 " + formatWan(topProduct.revenue) + "，占累计订单金额 " +
      topProduct.share_pct.toFixed(1) + "%。月度营收和毛利趋势见图表。";
  } else {
    aiConclusion.value = "截至 10 月 29 日，本月订单金额 " + formatWan(month.revenue) +
      "，较 9 月同期" + growthWord + Math.abs(month.growth_pct).toFixed(1) +
      "%；毛利率 " + month.gross_margin_pct.toFixed(1) + "%，活跃客户 " +
      month.active_customers + " 家。";
  }
  latestQuestion.value = prompt;
  analysisSource.value = "演示数据 · chatbi_sales.csv · " + demoSummary.totals.order_count + " 笔订单";
  insightItems.value = [
    { kind: "positive", label: "区域表现", title: topRegion.name + "当前领先", detail: "本月订单金额占比 " + topRegion.share_pct.toFixed(1) + "%，合计 " + formatWan(topRegion.revenue) + "。", icon: TrendingUp, time: formatTime(new Date()) },
    { kind: "warning", label: "待回款", title: demoSummary.totals.unpaid_order_count + " 笔订单待回款", detail: "演示数据应收金额 " + formatWan(demoSummary.totals.open_receivables) + "。", icon: AlertTriangle, time: formatTime(new Date()) },
    { kind: "neutral", label: "数据范围", title: demoSummary.totals.customer_count + " 家累计客户", detail: "订单覆盖 " + demoSummary.period.start + " 至 " + demoSummary.period.end + "。", icon: ShieldCheck, time: formatTime(new Date()) },
  ];
  updateCharts();
}
async function submitQuestion() {
  const prompt = question.value.trim();
  if (!prompt || isAnalyzing.value) return;
  question.value = "";
  latestQuestion.value = prompt;
  isAnalyzing.value = true;
  aiConclusion.value = "正在理解业务意图、匹配指标口径并生成查询计划…";
  analysisSource.value = "AI Agent 正在分析";
  selectSection("dashboard");
  if (liveAgentReady.value && datasourceReady.value) {
    try {
      const source = datasourceReady.value;
      if (!sessions.currentSession || sessions.currentSession.selected_datasource_id !== source.id) {
        await sessions.create("新分析", source.id);
      }
      const runId = await sessions.submitRun(prompt, makeIdempotencyKey());
      await runs.begin(runId);
      notify("分析任务已提交，正在生成证据链", "info");
      return;
    } catch (error) {
      notify(error instanceof Error ? error.message : "Agent 暂不可用，已切回演示分析", "warning");
      demoAnswer(prompt);
      isAnalyzing.value = false;
      return;
    }
  }
  try {
    analysisSource.value = "DeepSeek Responses · 流式输出";
    aiConclusion.value = "";
    const response = await fetch(buildApiUrl("/ai/deepseek/analyze"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: prompt }),
    });
    if (!response.ok || !response.body) throw new Error("DeepSeek 服务暂不可用");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let receivedText = false;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = frame.match(/^event:\s*(\w+)/m)?.[1];
        const data = frame.match(/^data:\s*(.+)$/m)?.[1];
        if (!event || !data) continue;
        const payload = JSON.parse(data) as { text?: string; message?: string };
        if (event === "delta" && payload.text) {
          receivedText = true;
          aiConclusion.value += payload.text;
        }
        if (event === "error") throw new Error(payload.message ?? "DeepSeek 分析失败");
      }
    }
    if (receivedText) {
      isAnalyzing.value = false;
      notify("DeepSeek 分析完成，可继续追问");
      return;
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : "DeepSeek 暂不可用，已切回演示分析", "warning");
  }
  aiConclusion.value = "正在使用本地演示数据生成可复现的分析结果…";
  window.setTimeout(() => {
    demoAnswer(prompt);
    isAnalyzing.value = false;
    notify("演示分析已完成，可继续追问");
  }, 1050);
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
function openDatasources() { void router.push("/datasources"); }
function openModelSettings() { void router.push("/settings/model"); }
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
  if (status === "succeeded") {
    analysisSource.value = "受控分析引擎 · 已完成执行并登记产物";
    const sessionId = sessions.currentSession?.id;
    if (sessionId) {
      await sessions.select(sessionId);
      const reply = [...sessions.messages].reverse().find((item: Message) => item.role === "assistant");
      if (reply?.content_text) aiConclusion.value = reply.content_text;
    }
    notify("分析完成，结论与证据已更新");
  } else {
    aiConclusion.value = runs.currentRun?.error_message ?? "本次分析未能完整完成，请检查数据源配置或查看运行详情。";
    analysisSource.value = "运行状态 · 请检查执行记录";
    notify("分析结束，请检查运行状态", "warning");
  }
});
onMounted(async () => {
  initCharts();
  await Promise.allSettled([datasources.load(), models.load(), sessions.load()]);
  if (liveAgentReady.value) analysisSource.value = "受控分析引擎 · 数据源已连接";
});
onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  trendChart?.dispose(); channelChart?.dispose(); regionChart?.dispose();
  if (toastTimer !== null) window.clearTimeout(toastTimer);
});
</script>

<template>
  <section class="chatbi-app" @pointermove.passive="setPointerGlow">
    <div class="ambient-glow ambient-a" aria-hidden="true" /><div class="ambient-glow ambient-b" aria-hidden="true" />
    <aside class="sidebar">
      <div class="brand-row"><img class="brand-mark chatbi-brand-logo" src="/chatbi-mark.svg" alt="智析 ChatBI 标识" /><div class="brand-name"><strong>智析 <span>ChatBI</span></strong><small>AI 企业数据分析平台</small></div><i class="brand-online" /></div>
      <button type="button" class="workspace-select interactive" @click="openDatasources"><span class="workspace-mark"><Database :size="16" /></span><span class="workspace-copy"><small>当前工作空间</small><strong>星河科技 · 总部</strong></span><ChevronDown :size="14" class="dim" /></button>
      <div class="side-label">分析空间</div>
      <nav class="side-nav" aria-label="工作空间导航">
        <button v-for="item in navItems" :key="item.id" type="button" class="nav-item interactive" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="17" /><span>{{ item.label }}</span><span v-if="item.id === 'reports'" class="nav-count">3</span><i v-if="activeSection === item.id" class="nav-active" /></button>
      </nav>
      <div class="side-divider" />
      <div class="side-label side-label-actions"><span>数据资源</span><button type="button" class="tiny-icon interactive" title="导入数据" @click="openUpload"><Plus :size="14" /></button></div>
      <button type="button" class="source-link interactive" @click="openDatasources"><i class="source-dot" /><span class="source-copy"><strong>{{ datasourceLabel }}</strong><small>{{ datasourceReady ? datasourceReady.type.toUpperCase() + ' · Schema 已就绪' : 'CSV · 906 条订单 · 2026.01—2026.10' }}</small></span><MoreHorizontal :size="15" class="dim" /></button>
      <div class="side-bottom"><div class="engine-card"><div class="engine-heading"><span class="engine-icon"><Sparkles :size="13" /></span><strong>AI 分析引擎</strong><em>{{ liveAgentReady ? "LIVE" : "DEMO" }}</em></div><p>{{ liveAgentReady ? activeModel?.model_name + " · 已激活" : "演示模式已就绪" }}</p><div class="engine-meter"><i /></div><small>{{ liveAgentReady ? "Agent · SQL 网关 · DataLink" : "连接数据源和模型以启用真实分析" }}</small></div><button type="button" class="profile-link interactive" @click="openModelSettings"><span class="avatar">Y</span><span><strong>运营分析师</strong><small>企业工作空间</small></span><MoreHorizontal :size="16" /></button></div>
    </aside>

    <main class="main-area">
      <header class="topbar"><div class="crumb"><span>工作空间</span><i>/</i><strong>{{ activeTitle }}</strong><span class="realtime"><i />实时</span></div><div class="top-actions"><div class="time-label"><i />{{ formatTime(lastUpdated) }} <span>·</span> 2026.10.29</div><button class="icon-action interactive" type="button" title="帮助中心" @click="notify('帮助中心即将开放，欢迎继续探索工作台', 'info')"><CircleHelp :size="17" /></button><button class="icon-action interactive" type="button" title="刷新数据" @click="refreshDashboard"><RefreshCw :size="16" /></button><button class="icon-action interactive notification-icon" type="button" title="3 条待处理提醒" @click="notify('当前有 3 条经营提醒待查看', 'warning')"><i /> <Activity :size="17" /></button><button type="button" class="primary-action interactive" @click="openUpload"><Upload :size="14" />导入数据</button></div></header>
      <div class="page-scroll"><div class="page-content">
        <template v-if="activeSection === 'dashboard' || activeSection === 'query'">
          <section class="page-heading"><div><div class="eyebrow"><i />{{ activeSection === "query" ? "NATURAL LANGUAGE ANALYTICS" : "THURSDAY, OCTOBER 29, 2026 · 经营总览" }}</div><h1>{{ greeting }}，让数据 <span>回答问题。</span></h1><p>用自然语言探索业务，让每一份洞察都有据可查。</p></div><button type="button" class="date-range interactive" @click="notify('当前展示 2026 年 10 月经营数据', 'info')"><Clock3 :size="15" />2026年10月<ChevronDown :size="13" /></button></section>
          <section class="metric-grid" aria-label="核心经营指标">
            <article v-for="(metric, index) in metrics" :key="metric.label" class="metric-card interactive" :class="'metric-' + metric.color" :style="{ '--card-index': index }"><div class="metric-top"><span>{{ metric.label }}</span><i><component :is="metric.icon" :size="16" /></i></div><div class="metric-value-row"><strong>{{ metric.value }}</strong><svg class="mini-spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><path :d="metric.spark" /></svg></div><div class="metric-foot"><span class="metric-change"><ArrowUpRight :size="13" />{{ metric.change }}</span><span>{{ metric.foot }}</span><small>近30天</small></div><i class="metric-accent" /></article>
          </section>
          <section class="main-grid">
            <article class="panel trend-panel"><header class="panel-heading"><div><div class="panel-kicker"><i />经营表现</div><h2>营收趋势分析 <span>·</span> <small>Revenue Overview</small></h2></div><div class="panel-tools"><span class="live-pill"><i />实时数据</span><button type="button" class="menu-button interactive" aria-label="营收趋势选项" @click="notify('图表展示 2026 年 1 月至 10 月月度营收和毛利', 'info')"><MoreHorizontal :size="18" /></button></div></header><div class="trend-total"><strong>{{ formatWan(latestDemoMonth.revenue) }}</strong><span :class="{ down: latestDemoMonth.growth_pct < 0 }"><ArrowUpRight v-if="latestDemoMonth.growth_pct >= 0" :size="14" /><ArrowDownRight v-else :size="14" />{{ latestDemoMonth.growth_pct >= 0 ? '+' : '' }}{{ latestDemoMonth.growth_pct.toFixed(1) }}%</span><em>10 月 1 日—{{ latestDemoMonth.as_of_day }} 日 · 较 9 月同期</em></div><div ref="trendHost" class="trend-chart" role="img" aria-label="2026年1月至10月每月营收和毛利趋势图" /><div class="chart-foot"><span><i class="legend-dot cyan" />月度营收与毛利 · 2026年</span><span>更新于 {{ formatTime(lastUpdated) }}</span><button type="button" @click="selectSection('reports')">查看分析 <ArrowUpRight :size="13" /></button></div></article>
            <article class="panel insight-panel"><header class="panel-heading"><div><div class="panel-kicker"><Sparkles :size="13" />AI 智能洞察</div><h2>值得关注的信号</h2></div><button type="button" class="text-action interactive" @click="selectSection('reports')">全部洞察 <ArrowUpRight :size="13" /></button></header><div class="briefing"><span class="briefing-orb"><BrainCircuit :size="19" /></span><div><small>AI DAILY BRIEFING</small><p>截至 10 月 29 日，订单金额较 9 月同期<strong>{{ latestDemoMonth.growth_pct >= 0 ? "增长" : "下降" }} {{ Math.abs(latestDemoMonth.growth_pct).toFixed(1) }}%</strong>。</p></div></div><div class="insight-list"><button v-for="item in insightItems" :key="item.title" type="button" class="insight-row interactive" :class="'insight-' + item.kind" @click="notify(item.detail, item.kind === 'warning' ? 'warning' : 'info')"><i class="insight-symbol"><component :is="item.icon" :size="15" /></i><span class="insight-body"><span class="insight-row-meta"><em>{{ item.label }}</em><small>{{ item.time }}</small></span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span><ArrowUpRight :size="14" class="insight-arrow" /></button></div><button type="button" class="weekly-link interactive" @click="selectSection('reports')"><span><Lightbulb :size="14" />演示数据包含 <strong>{{ demoSummary.totals.order_count }}</strong> 笔可追溯订单</span><ArrowUpRight :size="14" /></button></article>
          </section>
          <section class="query-dock" :class="{ analyzing: isAnalyzing }"><div class="query-head"><div class="query-title"><span><Sparkles :size="14" /></span><strong>问问你的数据</strong><em>AI POWERED</em></div><button type="button" class="query-source interactive" @click="openDatasources"><Database :size="13" />{{ datasourceLabel }}<ChevronDown :size="13" /></button></div><div class="query-input-row"><textarea ref="queryInput" v-model="question" rows="1" aria-label="输入数据分析问题" placeholder="试试问：截至 10 月 29 日，各区域营收占比和回款情况如何？" @keydown.enter.exact.prevent="submitQuestion" /><div class="query-tools"><button type="button" class="add-question interactive" title="上传数据" @click="openUpload"><Plus :size="17" /></button><i /><button type="button" class="send-button interactive" :disabled="!question.trim() || isAnalyzing" :aria-label="isAnalyzing ? '正在分析' : '发送问题'" @click="submitQuestion"><span v-if="isAnalyzing" class="spinner" /><Send v-else :size="15" /></button></div></div><div class="query-foot"><div class="prompt-list"><span>试试</span><button v-for="prompt in prompts" :key="prompt" type="button" class="prompt-chip interactive" @click="setPrompt(prompt)">{{ prompt }}</button></div><span class="secure-note"><ShieldCheck :size="12" />只读分析 · 数据安全</span></div></section>
          <section class="answer-card"><span class="answer-glyph"><Sparkles :size="16" /></span><div class="answer-body"><div><em>{{ isAnalyzing ? "ANALYZING" : "AI INSIGHT" }}</em><span><i />{{ analysisSource }}</span></div><p><strong>{{ latestQuestion }}</strong>{{ aiConclusion }}</p></div><button type="button" class="evidence-button interactive" @click="selectSection('reports')"><ShieldCheck :size="14" />查看证据 <span>↗</span></button></section>
          <section class="bottom-grid">
            <article class="panel channel-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">营收构成</div><h2>收入来源分布</h2></div><button type="button" class="menu-button interactive" @click="selectSection('reports')"><MoreHorizontal :size="18" /></button></header><div class="channel-content"><div ref="channelHost" class="channel-chart" role="img" aria-label="营收来源构成环图" /><div class="channel-legend"><button v-for="item in channelLegend" :key="item.name" type="button" class="interactive" @click="notify(item.name + '贡献本月订单金额 ' + item.value, 'info')"><i :class="item.color" />{{ item.name }}<strong>{{ item.value }}</strong></button></div></div></article>
            <article class="panel region-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">区域表现</div><h2>区域营收 TOP 5</h2></div><button type="button" class="range-mini interactive" @click="notify('已按本月营收由高到低排序', 'info')">本月 <ChevronDown :size="12" /></button></header><div ref="regionHost" class="region-chart" role="img" aria-label="区域营收前五名横向柱状图" /><div class="region-foot"><span><i class="legend-dot cyan" />10 月截至 29 日</span><strong>{{ leadingDemoRegion.name }} {{ leadingDemoRegion.share_pct.toFixed(1) }}%</strong><button type="button" @click="notify('区域排名按演示订单金额聚合', 'info')">数据口径 <CircleHelp :size="12" /></button></div></article>
            <article class="panel alert-panel"><header class="panel-heading compact-heading"><div><div class="panel-kicker">实时监测</div><h2>经营预警 <em class="alert-count">2</em></h2></div><button type="button" class="text-action interactive" @click="notify('已查看全部经营预警', 'info')">查看全部 <ArrowUpRight :size="13" /></button></header><button type="button" class="alert-row interactive" @click="notify('待回款金额 ' + formatWan(demoSummary.totals.open_receivables), 'warning')"><i><Clock3 :size="14" /></i><span><strong>{{ demoSummary.totals.unpaid_order_count }} 笔订单待回款</strong><small>应收金额 {{ formatWan(demoSummary.totals.open_receivables) }}</small></span><em>关注</em></button><button type="button" class="alert-row amber-alert interactive" @click="notify('10 月毛利率较 9 月同期变化 ' + latestDemoMonth.gross_profit_change_pct + '%', 'info')"><i><AlertTriangle :size="14" /></i><span><strong>当月毛利率 {{ latestDemoMonth.gross_margin_pct.toFixed(1) }}%</strong><small>毛利 {{ formatWan(latestDemoMonth.gross_profit) }} · 较上月同期 {{ latestDemoMonth.gross_profit_change_pct }}%</small></span><em>分析</em></button><div class="alert-foot"><span><i />监测规则运行正常</span><small>09:42 更新</small></div></article>
          </section>
          <footer class="page-footer"><span>智析 ChatBI <i>·</i> 让每个决策都有数据依据</span><span>Agent <i class="footer-agent" />{{ liveAgentReady ? "已连接" : "演示模式" }} <b>·</b> {{ runs.currentRun?.status === "running" ? "分析执行中" : runs.currentRun?.status === "succeeded" ? "刚刚完成一次分析" : "数据已同步" }}</span></footer>
        </template>

        <template v-else-if="activeSection === 'reports'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />AI GENERATED · EVIDENCE READY</div><h1>洞察报告 <span>一目了然。</span></h1><p>每份分析都包含清晰口径、证据引用和可追溯的运行记录。</p></div><button class="primary-action interactive" type="button" @click="downloadReport"><Download :size="14" />导出最新报告</button></section>
          <section class="panel report-hero"><div class="report-copy"><span class="report-label"><Sparkles :size="13" />AI 经营简报 · 2026.10</span><h2>{{ latestQuestion }}</h2><p>{{ aiConclusion }}</p><div class="report-meta"><span><Database :size="13" />{{ analysisSource }}</span><span><ShieldCheck :size="13" />证据链已核验</span></div><button type="button" class="primary-action interactive" @click="downloadReport"><FileText :size="14" />导出完整报告</button></div><div class="report-art"><i /><i /><span><BrainCircuit :size="31" /></span><em class="art-stat one"><small>Oct Revenue</small><strong>{{ (latestDemoMonth.growth_pct >= 0 ? "+" : "") + latestDemoMonth.growth_pct.toFixed(1) }}%</strong></em><em class="art-stat two"><small>Gross Margin</small><strong>{{ latestDemoMonth.gross_margin_pct.toFixed(1) }}%</strong></em></div></section>
          <section class="panel table-panel"><header class="panel-heading"><div><div class="panel-kicker">REPORT LIBRARY</div><h2>最近生成的报告</h2></div><button type="button" class="outline-action interactive" @click="notify('报告列表已更新')"><RefreshCw :size="14" />刷新</button></header><div class="data-table"><div class="table-row table-head"><span>报告名称</span><span>类型</span><span>生成时间</span><span>状态</span><span /></div><button v-for="row in reportRows" :key="row.title" type="button" class="table-row interactive" @click="downloadReport"><span class="report-name"><i><FileText :size="15" /></i><strong>{{ row.title }}</strong></span><span>{{ row.type }}</span><span>{{ row.time }}</span><span class="success-state"><Check :size="13" />已完成</span><Download :size="15" /></button></div></section>
        </template>

        <template v-else-if="activeSection === 'ledger'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />PROJECT CONTROL CENTER</div><h1>项目流程台账 <span>进度清晰。</span></h1><p>集中查看企业数据项目的负责人、当前阶段与交付节点。</p></div><button type="button" class="primary-action interactive" @click="notify('新建项目向导即将开放', 'info')"><Plus :size="14" />新建项目</button></section>
          <section class="stat-grid"><article v-for="stat in [{label:'进行中项目',value:'12',note:'较上季度 +3',tone:'cyan'},{label:'按期交付率',value:'91.6%',note:'高于目标 4.6%',tone:'green'},{label:'待处理节点',value:'08',note:'2 项即将到期',tone:'amber'},{label:'本月已交付',value:'06',note:'验收通过',tone:'violet'}]" :key="stat.label" class="panel stat-card"><span>{{ stat.label }}</span><strong>{{ stat.value }}</strong><small :class="stat.tone">{{ stat.note }}</small></article></section>
          <section class="panel table-panel"><header class="panel-heading"><div><div class="panel-kicker">ACTIVE PROJECTS</div><h2>项目进度追踪</h2></div><button type="button" class="outline-action interactive" @click="notify('台账已同步')"><RefreshCw :size="14" />同步台账</button></header><div class="data-table ledger-table"><div class="ledger-row table-head"><span>项目名称</span><span>负责人</span><span>当前阶段</span><span>整体进度</span><span>预计交付</span></div><button v-for="row in ledgerRows" :key="row.name" type="button" class="ledger-row interactive" @click="notify(row.name + ' · 当前进度 ' + row.progress + '%', 'info')"><span class="ledger-name"><i :class="row.color" /><strong>{{ row.name }}</strong></span><span>{{ row.owner }}</span><span><em class="stage-pill">{{ row.stage }}</em></span><span class="progress-cell"><i><b :class="row.color" :style="{ width: row.progress + '%' }" /></i><small>{{ row.progress }}%</small></span><span>{{ row.date }}</span></button></div></section>
          <section class="panel insight-note"><i><Lightbulb :size="16" /></i><div><strong>进度洞察</strong><p>数据资产接入与治理项目已进入联调验收阶段，预计可提前 3 天交付。智能经营分析一期关键路径正常，建议本周完成模型服务联调。</p></div><em><Sparkles :size="13" />AI 生成</em></section>
        </template>

        <template v-else-if="activeSection === 'finance'">
          <section class="page-heading module-heading"><div><div class="eyebrow"><i />FINANCE OVERVIEW</div><h1>收支管理 <span>收支一目了然。</span></h1><p>聚合收入、成本和现金流，及时发现经营变化。</p></div><button type="button" class="primary-action interactive" @click="notify('请选择 CSV 或 Excel 文件导入流水', 'info'); openUpload()"><Upload :size="14" />导入流水</button></section>
          <section class="finance-summary"><article class="panel net-cash"><div class="panel-kicker">本月净现金流</div><strong>¥ 2,184,760</strong><div class="net-foot"><span><ArrowUpRight :size="13" />14.2%</span><small>较上月同期</small><div><i v-for="(height, index) in [24,35,29,44,38,57,48,70,60,82,72,100]" :key="index" :style="{ height: height + '%' }" /></div></div></article><article class="panel finance-stat"><span>总收入</span><strong>¥2,864,320</strong><small><ArrowUpRight :size="13" />12.8% 环比</small></article><article class="panel finance-stat expense"><span>总支出</span><strong>¥679,560</strong><small><ArrowDownRight :size="13" />4.2% 环比</small></article></section>
          <section class="panel table-panel"><header class="panel-heading"><div><div class="panel-kicker">TRANSACTION LEDGER</div><h2>收支明细</h2></div><div class="table-actions"><button type="button" class="range-mini interactive" @click="notify('已筛选 2026 年 10 月记录', 'info')">2026年10月 <ChevronDown :size="12" /></button><button type="button" class="outline-action interactive" @click="downloadReport"><Download :size="14" />导出</button></div></header><div class="data-table"><div class="table-row table-head finance-row"><span>项目</span><span>分类</span><span>发生时间</span><span>金额</span><span>状态</span></div><button v-for="row in financeRows" :key="row.name" type="button" class="table-row finance-row interactive" @click="notify(row.name + ' · ' + row.state, 'info')"><span class="report-name"><i :class="row.positive ? 'income-icon' : 'expense-icon'"><ArrowDownRight v-if="row.positive" :size="14" /><ArrowUpRight v-else :size="14" /></i><strong>{{ row.name }}</strong></span><span>{{ row.category }}</span><span>{{ row.date }}</span><strong :class="row.positive ? 'amount-income' : 'amount-expense'">{{ row.positive ? '+' : '' }}¥{{ Math.abs(row.amount).toLocaleString() }}</strong><span class="success-state"><i />{{ row.state }}</span></button></div></section>
        </template>
      </div></div>
    </main>
    <Transition name="toast-spring"><div v-if="toast" class="toast" :class="'toast-' + toast.kind"><span><Check v-if="toast.kind === 'success'" :size="14" /><AlertTriangle v-else-if="toast.kind === 'warning'" :size="14" /><Sparkles v-else :size="14" /></span>{{ toast.message }}<button type="button" aria-label="关闭提示" @click="toast = null">×</button></div></Transition>
    <input ref="fileInput" class="visually-hidden" type="file" accept=".csv,.xlsx,.xls,.sqlite,.db" @change="handleFileSelected" />
  </section>
</template>

