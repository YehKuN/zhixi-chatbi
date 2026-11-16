<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowUpRight, Check, ChevronDown, Database, Ghost, ImagePlus, LoaderCircle, MessageSquareText,
  Moon, PanelLeftClose, PanelLeftOpen, Plus, RefreshCw, Send, Settings2, ShieldCheck, Sparkles, SquarePen,
  Stethoscope, Sun, Trash2,
} from "@lucide/vue";

import AskAmbientBackdrop from "@/components/AskAmbientBackdrop.vue";
import AskAnswerChart from "@/components/AskAnswerChart.vue";
import AskIntroOverlay from "@/components/AskIntroOverlay.vue";
import RichMarkdown from "@/components/RichMarkdown.vue";
import type { DataSource } from "@/api/types";
import { readAskIntroConfig, prefersReducedMotion } from "@/lib/askIntro";
import { useTheme } from "@/lib/theme";
import { clearStoredWallpaper, readStoredWallpaper, saveStoredWallpaper } from "@/lib/wallpaperStore";
import { useAuthStore } from "@/stores/authStore";
import { useDatasourceStore } from "@/stores/datasourceStore";
import { useModelStore } from "@/stores/modelStore";
import { useRunStore } from "@/stores/runStore";
import { useSessionStore } from "@/stores/sessionStore";

const WORKSPACE_STORAGE_KEY = "chatbi.ask.workspace";
const SIDEBAR_STORAGE_KEY = "chatbi.ask.sidebar";
/** 临时会话建出来的会话标题，侧栏历史不展示，与「不写入会话列表」提示保持一致。 */
const TEMPORARY_TITLE = "临时会话";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const datasources = useDatasourceStore();
const models = useModelStore();
const sessions = useSessionStore();
const runs = useRunStore();
const { isDark, toggleTheme } = useTheme();

const question = ref("");
const submitting = ref(false);
const pendingQuestion = ref<string | null>(null);
const actionError = ref<string | null>(null);
const threadMode = ref<"standard" | "temporary">("standard");
const workspaceMenuOpen = ref(false);
const modelMenuOpen = ref(false);
const activatingModelId = ref<string | null>(null);
const selectedWorkspaceId = ref<string | null>(readStoredWorkspace());
const sideHidden = ref(readStoredSidebarHidden());
const introConfig = readAskIntroConfig();
const introVisible = ref(introConfig.enabled && !prefersReducedMotion());
const introRevealing = ref(false);
const introFast = ref(false);
let introSafetyTimer: ReturnType<typeof setTimeout> | null = null;
if (introVisible.value) {
  introSafetyTimer = setTimeout(() => {
    introSafetyTimer = null;
    finishIntro();
  }, introConfig.duration + 600);
}
const composerInput = ref<HTMLTextAreaElement | null>(null);
const threadScroll = ref<HTMLElement | null>(null);
const wallpaperOpen = ref(false);
const wallpaperKind = ref<"image" | "video" | null>(null);
const wallpaperUrl = ref<string | null>(null);
const wallpaperName = ref("");
const wallpaperBusy = ref(false);
const wallpaperError = ref<string | null>(null);
const wallpaperInput = ref<HTMLInputElement | null>(null);
const WALLPAPER_MAX_BYTES = 80 * 1024 * 1024;
const deletingSessionId = ref<string | null>(null);
const confirmingSessionId = ref<string | null>(null);
let confirmDeleteTimer: ReturnType<typeof setTimeout> | null = null;
const feedback = ref("");
let feedbackTimer: ReturnType<typeof setTimeout> | null = null;

function readStoredWorkspace(): string | null {
  try {
    return localStorage.getItem(WORKSPACE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistWorkspace(id: string | null): void {
  try {
    if (id === null) localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    else localStorage.setItem(WORKSPACE_STORAGE_KEY, id);
  } catch {
    // 隐私模式下写入失败时仅保留内存状态。
  }
}

function applyWallpaper(blob: Blob, kind: "image" | "video", name: string): void {
  if (wallpaperUrl.value !== null) URL.revokeObjectURL(wallpaperUrl.value);
  wallpaperUrl.value = URL.createObjectURL(blob);
  wallpaperKind.value = kind;
  wallpaperName.value = name;
}

async function restoreWallpaper(): Promise<void> {
  const stored = await readStoredWallpaper();
  if (stored !== null) applyWallpaper(stored.blob, stored.kind, stored.name);
}

function toggleWallpaper(): void {
  wallpaperOpen.value = !wallpaperOpen.value;
  workspaceMenuOpen.value = false;
  modelMenuOpen.value = false;
  if (wallpaperOpen.value) wallpaperError.value = null;
}

async function handleWallpaperFile(event: Event): Promise<void> {
  const input = event.currentTarget;
  if (!(input instanceof HTMLInputElement) || input.files === null || input.files.length === 0) return;
  const file = input.files[0];
  input.value = "";
  const kind = file.type.startsWith("video/") ? "video" : file.type.startsWith("image/") ? "image" : null;
  if (kind === null) {
    wallpaperError.value = "只支持图片或视频文件";
    return;
  }
  if (file.size > WALLPAPER_MAX_BYTES) {
    wallpaperError.value = "文件太大，请控制在 80MB 以内";
    return;
  }
  wallpaperBusy.value = true;
  wallpaperError.value = null;
  const saved = await saveStoredWallpaper({ blob: file, kind, name: file.name, updatedAt: Date.now() });
  wallpaperBusy.value = false;
  if (!saved) {
    wallpaperError.value = "壁纸保存失败，可能是浏览器存储空间不足";
    return;
  }
  applyWallpaper(file, kind, file.name);
}

async function resetWallpaper(): Promise<void> {
  if (wallpaperUrl.value !== null) URL.revokeObjectURL(wallpaperUrl.value);
  wallpaperUrl.value = null;
  wallpaperKind.value = null;
  wallpaperName.value = "";
  wallpaperError.value = null;
  await clearStoredWallpaper();
}

function readStoredSidebarHidden(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "hidden";
  } catch {
    return false;
  }
}

function toggleSidebar(): void {
  sideHidden.value = !sideHidden.value;
  try {
    if (sideHidden.value) localStorage.setItem(SIDEBAR_STORAGE_KEY, "hidden");
    else localStorage.removeItem(SIDEBAR_STORAGE_KEY);
  } catch {
    // 隐私模式下写入失败时仅保留内存状态。
  }
  void nextTick(() => composerInput.value?.focus());
}

function handleIntroReveal(fast = false): void {
  introRevealing.value = true;
  introFast.value = fast;
}

function finishIntro(): void {
  if (introSafetyTimer !== null) {
    clearTimeout(introSafetyTimer);
    introSafetyTimer = null;
  }
  introRevealing.value = true;
  introVisible.value = false;
  void nextTick(() => composerInput.value?.focus());
}

const readyDatasources = computed(() => datasources.items.filter((item) =>
  (item.status === "ready" || item.status === "schema_ready") && item.mask_fields_confirmed,
));
const selectedWorkspace = computed<DataSource | null>(() =>
  readyDatasources.value.find((item) => item.id === selectedWorkspaceId.value)
  ?? readyDatasources.value[0]
  ?? null,
);
const activeModel = computed(() => models.items.find((item) => item.is_active) ?? null);
const messages = computed(() => sessions.messages.filter((message) => message.content_text.trim().length > 0));
const historyItems = computed(() => sessions.sessions.filter((item) => item.title !== TEMPORARY_TITLE));
const currentSessionId = computed(() => sessions.currentSession?.id ?? null);
const hasThread = computed(() => messages.value.length > 0 || pendingQuestion.value !== null);
const busy = computed(() => submitting.value || runs.isActive);
const streamingAnswer = computed(() => runs.projection?.answerDraft ?? "");
const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return "早上好";
  if (hour < 18) return "下午好";
  return "晚上好";
});
const runStatusText = computed(() => {
  const run = runs.currentRun;
  if (run === null) return "分析中";
  if (run.status === "queued") return "排队中";
  if (run.status === "running") return "分析中";
  if (run.status === "succeeded") {
    if (run.completion_kind === "partial") return "部分完成";
    if (run.completion_kind === "clarification") return "需补充信息";
    return "已完成";
  }
  if (run.status === "failed") return "未完成";
  if (run.status === "canceled") return "已取消";
  return "分析中";
});

function workspaceMeta(item: DataSource): string {
  const rows = (item.schema?.tables ?? []).reduce((sum, table) => sum + (table.row_count ?? 0), 0);
  return rows > 0 ? rows.toLocaleString("zh-CN") + " 条记录" : item.type.toUpperCase();
}

function sessionTime(value: string | null): string {
  if (value === null) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "昨天";
  const days = Math.floor((now.getTime() - date.getTime()) / 86_400_000);
  if (days < 7) return days + " 天前";
  return (date.getMonth() + 1) + "-" + String(date.getDate()).padStart(2, "0");
}

async function openSession(sessionId: string): Promise<void> {
  if (currentSessionId.value === sessionId) return;
  threadMode.value = "standard";
  actionError.value = null;
  pendingQuestion.value = null;
  submitting.value = false;
  runs.clear();
  await sessions.select(sessionId);
  const datasourceId = sessions.currentSession?.selected_datasource_id ?? null;
  if (datasourceId !== null && readyDatasources.value.some((item) => item.id === datasourceId)) {
    selectedWorkspaceId.value = datasourceId;
  }
  await nextTick();
  scrollToEnd();
  composerInput.value?.focus();
}

function reloadSessions(): void {
  void sessions.load();
}

function requestDeleteSession(sessionId: string): void {
  if (deletingSessionId.value !== null) return;
  if (confirmingSessionId.value === sessionId) {
    void deleteSession(sessionId);
    return;
  }
  confirmingSessionId.value = sessionId;
  if (confirmDeleteTimer !== null) clearTimeout(confirmDeleteTimer);
  confirmDeleteTimer = setTimeout(() => {
    confirmingSessionId.value = null;
    confirmDeleteTimer = null;
  }, 3000);
}

async function deleteSession(sessionId: string): Promise<void> {
  if (confirmDeleteTimer !== null) {
    clearTimeout(confirmDeleteTimer);
    confirmDeleteTimer = null;
  }
  confirmingSessionId.value = null;
  const wasCurrent = currentSessionId.value === sessionId;
  deletingSessionId.value = sessionId;
  actionError.value = null;
  try {
    await sessions.remove(sessionId);
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : "删除会话失败，请稍后重试。";
    deletingSessionId.value = null;
    return;
  }
  deletingSessionId.value = null;
  notify("已删除该会话");
  if (!wasCurrent) return;
  runs.clear();
  pendingQuestion.value = null;
  submitting.value = false;
  const datasourceId = sessions.currentSession?.selected_datasource_id ?? null;
  if (datasourceId !== null && readyDatasources.value.some((item) => item.id === datasourceId)) {
    selectedWorkspaceId.value = datasourceId;
  }
  await nextTick();
  scrollToEnd();
}

function selectWorkspace(id: string): void {
  selectedWorkspaceId.value = id;
  workspaceMenuOpen.value = false;
  persistWorkspace(id);
}

function notify(message: string): void {
  feedback.value = message;
  if (feedbackTimer !== null) clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => {
    feedback.value = "";
    feedbackTimer = null;
  }, 2200);
}

function resetThread(mode: "standard" | "temporary"): void {
  sessions.clearWorkspace();
  runs.clear();
  pendingQuestion.value = null;
  actionError.value = null;
  question.value = "";
  threadMode.value = mode;
  notify(mode === "temporary" ? "已进入临时会话，本次对话不写入会话列表" : "已开启新会话");
  void nextTick(() => composerInput.value?.focus());
}

function openDashboard(): void {
  void router.push("/workspace");
}

function openDatasources(): void {
  void router.push("/datasources");
}

function openSettings(): void {
  void router.push("/settings/model");
}

function openDiagnosis(): void {
  void router.push("/workspace?section=diagnosis");
}

function makeIdempotencyKey(): string {
  const id = globalThis.crypto?.randomUUID?.();
  return id ? `web-${id}` : `web-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

async function activateModel(modelId: string): Promise<void> {
  if (activatingModelId.value !== null) return;
  activatingModelId.value = modelId;
  actionError.value = null;
  try {
    await models.activate(modelId);
    modelMenuOpen.value = false;
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : "模型切换失败";
  } finally {
    activatingModelId.value = null;
  }
}

async function submitQuestion(): Promise<void> {
  const text = question.value.trim();
  if (text.length === 0 || busy.value) return;
  const workspace = selectedWorkspace.value;
  if (workspace === null) {
    actionError.value = "请先在数据资产中连接并确认一个可分析的数据源。";
    return;
  }
  if (activeModel.value === null) {
    actionError.value = "请先在模型设置中配置并激活分析模型。";
    return;
  }
  actionError.value = null;
  submitting.value = true;
  pendingQuestion.value = text;
  question.value = "";
  await nextTick();
  scrollToEnd();
  try {
    if (sessions.currentSession === null || sessions.currentSession.selected_datasource_id !== workspace.id) {
      await sessions.create(threadMode.value === "temporary" ? TEMPORARY_TITLE : "新分析", workspace.id);
    }
    const runId = await sessions.submitRun(text, makeIdempotencyKey());
    await runs.begin(runId);
  } catch (caught) {
    submitting.value = false;
    pendingQuestion.value = null;
    question.value = text;
    actionError.value = caught instanceof Error ? caught.message : "提交分析失败，请稍后重试。";
  }
}

function onComposerKeydown(event: KeyboardEvent): void {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  void submitQuestion();
}

function scrollToEnd(): void {
  const element = threadScroll.value;
  if (element !== null) element.scrollTop = element.scrollHeight;
}

function closeMenus(): void {
  workspaceMenuOpen.value = false;
  modelMenuOpen.value = false;
  wallpaperOpen.value = false;
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  if (introVisible.value) {
    finishIntro();
    return;
  }
  closeMenus();
}

watch(selectedWorkspaceId, (id) => persistWorkspace(id));
watch(() => messages.value.length, async () => {
  await nextTick();
  scrollToEnd();
});
watch(() => runs.currentRun?.status, async (status) => {
  if (status !== "succeeded" && status !== "failed" && status !== "canceled") return;
  submitting.value = false;
  const sessionId = sessions.currentSession?.id ?? null;
  if (sessionId !== null) {
    try {
      await sessions.select(sessionId);
    } catch {
      // 会话刷新失败时保留当前消息，仅提示运行结果。
    }
  }
  pendingQuestion.value = null;
  if (status !== "succeeded") {
    actionError.value = runs.currentRun?.error_message ?? "本次分析未完成，请检查数据源连接或稍后重试。";
  } else if (runs.currentRun?.completion_kind === "clarification") {
    actionError.value = "这次问题还需要补充范围，试着补充时间区间或对比维度。";
  }
  await nextTick();
  scrollToEnd();
});

onMounted(async () => {
  window.addEventListener("keydown", onGlobalKeydown);
  void restoreWallpaper();
  await Promise.allSettled([datasources.load(), models.load(), sessions.load()]);
  const requested = route.query.workspace;
  if (typeof requested === "string" && readyDatasources.value.some((item) => item.id === requested)) {
    selectedWorkspaceId.value = requested;
    void router.replace({ path: "/ask" });
  }
  if (selectedWorkspaceId.value === null
    || !readyDatasources.value.some((item) => item.id === selectedWorkspaceId.value)) {
    selectedWorkspaceId.value = readyDatasources.value[0]?.id ?? null;
  }
  persistWorkspace(selectedWorkspaceId.value);
  // 从驾驶舱或数据资产往返时保留当前会话，避免已完成的问答被清空；没有会话时只清理残留运行态。
  if (sessions.currentSession === null) {
    runs.clear();
  }
  await nextTick();
  if (messages.value.length > 0) scrollToEnd();
  composerInput.value?.focus();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKeydown);
  if (feedbackTimer !== null) clearTimeout(feedbackTimer);
  if (confirmDeleteTimer !== null) clearTimeout(confirmDeleteTimer);
  if (wallpaperUrl.value !== null) URL.revokeObjectURL(wallpaperUrl.value);
});
</script>

<template>
  <section
    class="ask-studio"
    :class="{ 'is-dark': isDark, 'has-wallpaper': wallpaperUrl !== null, 'intro-hold': introVisible && !introRevealing, 'intro-reveal': introVisible && introRevealing, 'intro-fast': introVisible && introFast }"
  >
    <div class="ask-wallpaper" aria-hidden="true">
      <i class="wall-glow glow-a" /><i class="wall-glow glow-b" /><i class="wall-glow glow-c" /><i class="wall-grid" />
    </div>

    <div v-if="wallpaperUrl !== null" class="ask-wallpaper-layer" aria-hidden="true">
      <img v-if="wallpaperKind === 'image'" :src="wallpaperUrl" alt="" />
      <video v-else :src="wallpaperUrl" autoplay loop muted playsinline />
      <div class="ask-wallpaper-scrim" />
    </div>

    <aside class="ask-side" :class="{ hidden: sideHidden }" :inert="sideHidden" aria-label="智能问数导航">
      <button type="button" class="ask-brand" title="返回经营驾驶舱" @click="openDashboard">
        <img src="/chatbi-mark.svg" alt="" aria-hidden="true" />
        <span class="brand-copy"><strong>智析 ChatBI</strong><small>智能问数工作台</small></span>
      </button>

      <button type="button" class="ask-new" @click="resetThread('standard')">
        <SquarePen :size="15" /><span>新会话</span>
      </button>

      <div class="ask-side-head">
        <span>工作区</span>
        <button type="button" class="ask-mini" aria-label="接入数据源" title="接入数据源" @click="openDatasources">
          <Plus :size="13" />
        </button>
      </div>

      <div class="ask-workspace-list">
        <button
          v-for="item in readyDatasources"
          :key="item.id"
          type="button"
          class="ask-workspace"
          :class="{ active: selectedWorkspace?.id === item.id }"
          :title="item.name"
          @click="selectWorkspace(item.id)"
        >
          <span class="ws-icon"><Database :size="14" /></span>
          <span class="ws-copy"><strong>{{ item.name }}</strong><small>{{ workspaceMeta(item) }}</small></span>
          <Check v-if="selectedWorkspace?.id === item.id" :size="13" class="ws-check" />
        </button>
        <button v-if="readyDatasources.length === 0" type="button" class="ask-workspace" title="接入数据源" @click="openDatasources">
          <span class="ws-icon"><Plus :size="14" /></span>
          <span class="ws-copy"><strong>接入数据源</strong><small>尚未连接真实数据</small></span>
        </button>
      </div>

      <div class="ask-side-head">
        <span>历史会话</span>
        <button type="button" class="ask-mini" aria-label="刷新历史会话" title="刷新历史会话" @click="reloadSessions">
          <RefreshCw :size="12" />
        </button>
      </div>

      <div class="ask-session-list">
        <button
          v-for="item in historyItems"
          :key="item.id"
          type="button"
          class="ask-session"
          :class="{ active: item.id === currentSessionId }"
          :title="item.title"
          @click="openSession(item.id)"
        >
          <MessageSquareText :size="13" class="ss-icon" />
          <span class="ss-copy">
            <strong>{{ item.title }}</strong>
            <small>{{ sessionTime(item.last_message_at ?? item.updated_at) }}</small>
          </span>
          <span
            class="ss-del"
            :class="{ confirming: confirmingSessionId === item.id, busy: deletingSessionId === item.id }"
            role="button"
            tabindex="0"
            :title="confirmingSessionId === item.id ? '再点一次确认删除' : '删除会话'"
            :aria-label="confirmingSessionId === item.id ? '确认删除会话' : '删除会话'"
            @click.stop="requestDeleteSession(item.id)"
            @keydown.enter.stop.prevent="requestDeleteSession(item.id)"
            @keydown.space.stop.prevent="requestDeleteSession(item.id)"
          >
            <LoaderCircle v-if="deletingSessionId === item.id" :size="12" class="ss-spin" />
            <span v-else-if="confirmingSessionId === item.id">确认</span>
            <Trash2 v-else :size="12" />
          </span>
        </button>
        <p v-if="historyItems.length === 0" class="ask-session-empty">
          {{ sessions.loading ? "正在加载会话…" : "还没有历史会话，提问后会自动出现在这里。" }}
        </p>
        <p v-else-if="sessions.error" class="ask-session-empty">{{ sessions.error }}</p>
      </div>

      <div class="ask-side-bottom">
        <button type="button" class="ask-side-link" :class="{ active: threadMode === 'temporary' }" title="临时会话" @click="resetThread('temporary')">
          <Ghost :size="15" /><span>临时会话</span>
        </button>
        <button type="button" class="ask-side-link" title="设置" @click="openSettings">
          <Settings2 :size="15" /><span>设置</span>
        </button>
        <div class="ask-user">
          <span class="ask-avatar">{{ auth.avatarText }}</span>
          <span class="ask-user-copy">
            <strong>{{ auth.user?.display_name ?? "未登录" }}</strong>
            <small>{{ auth.enterprise?.name ?? "未绑定企业" }}</small>
          </span>
        </div>
      </div>
    </aside>

    <main class="ask-main">
      <AskAmbientBackdrop v-if="wallpaperUrl === null" />
      <header class="ask-top">
        <div class="ask-top-left">
          <button
            type="button"
            class="ask-side-toggle"
            :title="sideHidden ? '显示侧边栏' : '隐藏侧边栏，进入全屏'"
            :aria-label="sideHidden ? '显示侧边栏' : '隐藏侧边栏'"
            :aria-expanded="!sideHidden"
            @click="toggleSidebar"
          >
            <PanelLeftOpen v-if="sideHidden" :size="15" />
            <PanelLeftClose v-else :size="15" />
          </button>
          <span class="ask-live" :class="{ temp: threadMode === 'temporary' }"><i />{{ threadMode === "temporary" ? "临时会话 · 不写入会话列表" : "智能问数" }}</span>
        </div>
        <div class="ask-top-actions">
          <div class="ask-wallpaper-wrap">
            <button
              type="button"
              class="ask-wallpaper-btn"
              :class="{ active: wallpaperOpen }"
              :title="wallpaperUrl ? '背景设置 · 已启用自定义壁纸' : '背景设置'"
              aria-label="背景设置"
              @click="toggleWallpaper"
            >
              <ImagePlus :size="15" />
            </button>
            <div v-if="wallpaperOpen" class="ask-wallpaper-pop" role="dialog" aria-label="背景设置">
              <div class="wp-head"><strong>背景设置</strong><span>{{ wallpaperName || "默认渐变背景" }}</span></div>
              <div class="wp-preview">
                <video v-if="wallpaperKind === 'video' && wallpaperUrl !== null" :src="wallpaperUrl" autoplay loop muted playsinline />
                <img v-else-if="wallpaperKind === 'image' && wallpaperUrl !== null" :src="wallpaperUrl" alt="当前壁纸" />
                <span v-else>暂无自定义壁纸</span>
              </div>
              <div class="wp-actions">
                <button type="button" class="wp-primary" :disabled="wallpaperBusy" @click="wallpaperInput?.click()">
                  <LoaderCircle v-if="wallpaperBusy" :size="13" class="ask-spin" /><ImagePlus v-else :size="13" />导入壁纸
                </button>
                <button type="button" class="wp-ghost" :disabled="wallpaperUrl === null" @click="resetWallpaper">恢复默认</button>
              </div>
              <p class="wp-hint">支持 JPG / PNG / GIF / MP4 / WebM，动图与视频自动循环播放。</p>
              <p v-if="wallpaperError" class="wp-error">{{ wallpaperError }}</p>
              <input ref="wallpaperInput" type="file" accept="image/*,video/mp4,video/webm" hidden @change="handleWallpaperFile" />
            </div>
          </div>
          <span class="ask-model-state">{{ activeModel ? activeModel.model_name : "尚未激活模型" }}</span>
          <button
            type="button"
            class="ask-theme"
            :title="isDark ? '切换日间模式' : '切换夜间模式'"
            :aria-label="isDark ? '切换日间模式' : '切换夜间模式'"
            @click="toggleTheme"
          >
            <Sun v-if="isDark" :size="15" />
            <Moon v-else :size="15" />
          </button>
          <button type="button" class="ask-ghost" @click="openDashboard">经营驾驶舱<ArrowUpRight :size="12" /></button>
        </div>
      </header>

      <div class="ask-body" :class="{ 'has-thread': hasThread }">
        <div v-if="hasThread" ref="threadScroll" class="ask-thread">
          <div class="ask-thread-inner">
            <template v-for="message in messages" :key="message.id">
              <div v-if="message.role === 'user'" class="ask-bubble">{{ message.content_text }}</div>
              <article v-else class="ask-answer">
                <div class="ask-answer-label"><Sparkles :size="13" />智析</div>
                <RichMarkdown :content="message.content_text" answer />
                <AskAnswerChart v-if="message.run_id" :run-id="message.run_id" @rendered="scrollToEnd" />
              </article>
            </template>
            <div v-if="pendingQuestion !== null" class="ask-bubble">{{ pendingQuestion }}</div>
            <article v-if="pendingQuestion !== null" class="ask-answer streaming">
              <div class="ask-answer-label"><Sparkles :size="13" />智析<em>{{ runStatusText }}</em></div>
              <RichMarkdown v-if="streamingAnswer" :content="streamingAnswer" answer streaming />
              <div v-else class="ask-thinking"><i /><i /><i /><span>正在理解业务意图并生成只读查询…</span></div>
            </article>
          </div>
        </div>

        <div v-else class="ask-hero">
          <h1>{{ greeting }}，想让数据 <em>回答什么？</em></h1>
          <p>{{ threadMode === "temporary" ? "临时会话 · 本次对话不写入会话列表，提交后仍会生成可审计的运行记录" : selectedWorkspace ? "当前工作区：" + selectedWorkspace.name + " · 结论、SQL 与证据全程可追溯" : "连接真实数据源，用一句中文问题完成取数、分析与解释" }}</p>
        </div>

        <div class="ask-dock">
          <div class="ask-modes" role="tablist" aria-label="分析模式">
            <button type="button" role="tab" aria-selected="true" class="active"><MessageSquareText :size="13" />智能问数</button>
            <button type="button" role="tab" aria-selected="false" @click="openDiagnosis"><Stethoscope :size="13" />经营诊断</button>
          </div>

          <form class="ask-composer" @submit.prevent="submitQuestion">
            <textarea
              ref="composerInput"
              v-model="question"
              rows="2"
              :placeholder="selectedWorkspace ? '描述你想分析的业务问题，例如：对比 5 月和 11 月的购买转化率表现' : '先接入数据源，再开始提问…'"
              aria-label="输入数据分析问题"
              @keydown="onComposerKeydown"
            />
            <div class="ask-composer-foot">
              <div class="ask-menu-wrap">
                <button
                  type="button"
                  class="ask-pill"
                  :class="{ open: workspaceMenuOpen }"
                  @click="workspaceMenuOpen = !workspaceMenuOpen; modelMenuOpen = false; wallpaperOpen = false"
                >
                  <Database :size="13" /><span class="pill-label">{{ selectedWorkspace?.name ?? "选择工作区" }}</span><ChevronDown :size="12" class="pill-caret" />
                </button>
                <div v-if="workspaceMenuOpen" class="ask-pop left">
                  <div class="ask-pop-label">数据来源</div>
                  <button
                    v-for="item in readyDatasources"
                    :key="item.id"
                    type="button"
                    class="ask-pop-item"
                    :class="{ active: selectedWorkspace?.id === item.id }"
                    @click="selectWorkspace(item.id)"
                  >
                    <Database :size="13" />
                    <span class="pop-copy"><strong>{{ item.name }}</strong><small>{{ workspaceMeta(item) }}</small></span>
                    <Check v-if="selectedWorkspace?.id === item.id" :size="13" />
                  </button>
                  <div v-if="readyDatasources.length === 0" class="ask-pop-empty">尚未连接可分析的数据源</div>
                  <button type="button" class="ask-pop-item action" @click="openDatasources">
                    <Plus :size="13" /><span class="pop-copy"><strong>管理数据资产</strong></span>
                  </button>
                </div>
              </div>

              <div class="ask-menu-wrap model">
                <button
                  type="button"
                  class="ask-pill"
                  :class="{ open: modelMenuOpen }"
                  @click="modelMenuOpen = !modelMenuOpen; workspaceMenuOpen = false; wallpaperOpen = false"
                >
                  <Sparkles :size="13" /><span class="pill-label">{{ activeModel?.model_name ?? "模型未激活" }}</span><ChevronDown :size="12" class="pill-caret" />
                </button>
                <div v-if="modelMenuOpen" class="ask-pop right">
                  <div class="ask-pop-label">模型版本</div>
                  <button
                    v-for="item in models.items"
                    :key="item.id"
                    type="button"
                    class="ask-pop-item"
                    :class="{ active: item.is_active }"
                    :disabled="activatingModelId !== null"
                    @click="activateModel(item.id)"
                  >
                    <LoaderCircle v-if="activatingModelId === item.id" :size="13" class="ask-spin" />
                    <Sparkles v-else :size="13" />
                    <span class="pop-copy"><strong>{{ item.model_name }}</strong><small>{{ item.name }} · {{ item.provider }}</small></span>
                    <Check v-if="item.is_active" :size="13" />
                  </button>
                  <div v-if="models.items.length === 0" class="ask-pop-empty">尚未配置模型</div>
                  <button type="button" class="ask-pop-item action" @click="openSettings">
                    <Settings2 :size="13" /><span class="pop-copy"><strong>模型设置</strong></span>
                  </button>
                </div>
              </div>

              <button type="submit" class="ask-send" :disabled="question.trim().length === 0 || busy" :aria-label="busy ? '正在分析' : '发送问题'">
                <LoaderCircle v-if="busy" :size="15" class="ask-spin" /><Send v-else :size="15" />
              </button>
            </div>
            <div class="ask-composer-note"><span><ShieldCheck :size="12" />只读分析 · 数据安全</span><span>Enter 发送 · Shift + Enter 换行</span></div>
          </form>

          <p v-if="actionError" class="ask-error">{{ actionError }}</p>
          <p v-else-if="selectedWorkspace === null" class="ask-hint">还没有可分析的数据源，<button type="button" @click="openDatasources">前往数据资产接入</button></p>
          <p v-else-if="activeModel === null" class="ask-hint">还没有激活的分析模型，<button type="button" @click="openSettings">前往模型设置激活</button></p>
        </div>
      </div>

      <div v-if="workspaceMenuOpen || modelMenuOpen || wallpaperOpen" class="ask-pop-backdrop" @click="closeMenus" />
    </main>

    <AskIntroOverlay
      v-if="introVisible"
      :config="introConfig"
      @reveal="handleIntroReveal"
      @done="finishIntro"
    />

    <Transition name="ask-toast">
      <div v-if="feedback" class="ask-toast" role="status">{{ feedback }}</div>
    </Transition>
  </section>
</template>

<style scoped>
.ask-studio {
  --ask-ink: #2b3444;
  --ask-ink-soft: #5c6879;
  --ask-muted: #8b96a8;
  --ask-line: rgba(28, 43, 68, 0.08);
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 320px;
  overflow: hidden;
  background: #f4f7fc;
  color: var(--ask-ink);
  font-family: "Manrope", "Noto Sans SC", Inter, system-ui, sans-serif;
}

.ask-wallpaper {
  position: absolute;
  z-index: 0;
  inset: 0;
  background:
    radial-gradient(1200px 700px at 12% -10%, #e8f0ff 0%, transparent 60%),
    radial-gradient(900px 600px at 92% 8%, #f6ecff 0%, transparent 55%),
    radial-gradient(900px 700px at 60% 110%, #e3f4fb 0%, transparent 55%),
    linear-gradient(150deg, #f8fafd 0%, #eef3fa 48%, #e9eff8 100%);
}
.ask-wallpaper-layer {
  position: absolute;
  z-index: 0;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.ask-wallpaper-layer > img,
.ask-wallpaper-layer > video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ask-wallpaper-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(248, 251, 255, .82), rgba(243, 247, 252, .9));
}
.ask-studio.has-wallpaper .ask-hero h1 { color: #1d2534; }
.ask-studio.has-wallpaper .ask-hero p { color: #4d5870; }
.ask-studio.has-wallpaper .ask-model-state { color: #55617a; }
.ask-studio.has-wallpaper .ask-live { color: #3f4a5c; }
.ask-studio.is-dark.has-wallpaper .ask-hero h1 { color: #eef3fb; }
.ask-studio.is-dark.has-wallpaper .ask-hero p { color: #b9c5d6; }
.ask-studio.is-dark.has-wallpaper .ask-model-state { color: #a8b2c2; }
.ask-studio.is-dark.has-wallpaper .ask-live { color: #c9d3e1; }
.ask-studio.is-dark .ask-wallpaper-scrim {
  background: linear-gradient(180deg, rgba(7, 15, 26, .55), rgba(7, 15, 26, .72));
}
.wall-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.55;
}
.glow-a { top: -220px; left: 18%; width: 520px; height: 520px; background: #dbe7ff; }
.glow-b { top: 80px; right: -160px; width: 460px; height: 460px; background: #f0e4ff; }
.glow-c { bottom: -260px; left: 45%; width: 620px; height: 420px; background: #dff1fb; }
.wall-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(40, 60, 90, 0.028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(40, 60, 90, 0.028) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(ellipse at 50% 30%, rgba(0, 0, 0, 0.55), transparent 72%);
}

.ask-side {
  position: relative;
  z-index: 2;
  display: flex;
  width: 236px;
  min-width: 236px;
  height: 100%;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.52);
  padding: 20px 14px 16px;
  box-shadow: 1px 0 0 rgba(255, 255, 255, 0.75), 10px 0 40px rgba(35, 52, 82, 0.045);
  backdrop-filter: blur(26px) saturate(140%);
  -webkit-backdrop-filter: blur(26px) saturate(140%);
  transition: width 0.26s ease, min-width 0.26s ease, padding 0.26s ease, opacity 0.2s ease;
}
.ask-side.hidden {
  width: 0;
  min-width: 0;
  overflow: hidden;
  padding-right: 0;
  padding-left: 0;
  box-shadow: none;
  opacity: 0;
  pointer-events: none;
}

/* 入场动画期间由父级状态控制主界面显隐，动画层卸载后类名一并移除，保证最终完全可见。 */
.ask-studio.intro-hold .ask-side,
.ask-studio.intro-hold .ask-main {
  opacity: 0;
  transform: translateY(16px);
}
.ask-studio.intro-reveal .ask-side,
.ask-studio.intro-reveal .ask-main {
  opacity: 1;
  transform: none;
  transition: opacity 0.9s ease, transform 0.9s cubic-bezier(0.22, 0.61, 0.36, 1);
}
.ask-studio.intro-reveal.intro-fast .ask-side,
.ask-studio.intro-reveal.intro-fast .ask-main {
  transition-duration: 0.3s;
}

.ask-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 0;
  background: transparent;
  padding: 2px 4px;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.ask-brand img { width: 26px; height: 26px; object-fit: contain; }
.brand-copy { display: grid; gap: 1px; }
.brand-copy strong { color: #222b3a; font-size: 13.5px; font-weight: 650; letter-spacing: -0.2px; }
.brand-copy small { color: var(--ask-muted); font-size: 10px; letter-spacing: 0.3px; }

.ask-new {
  display: flex;
  height: 38px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-top: 22px;
  border: 1px solid rgba(28, 43, 68, 0.08);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 1px 2px rgba(30, 45, 70, 0.04);
  color: #3c4657;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.25s ease, border-color 0.25s ease, color 0.25s ease, transform 0.25s ease, box-shadow 0.25s ease;
}
.ask-new:hover {
  border-color: rgba(80, 105, 215, 0.24);
  background: #fff;
  box-shadow: 0 8px 20px rgba(35, 52, 82, 0.08);
  color: #3b4dc0;
  transform: translateY(-1px);
}

.ask-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 24px 4px 8px;
  color: var(--ask-muted);
  font-size: 11px;
  letter-spacing: 0.4px;
}
.ask-mini {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--ask-muted);
  cursor: pointer;
}
.ask-mini:hover { background: rgba(28, 43, 68, 0.06); color: #3c4657; }

.ask-workspace-list { display: flex; flex: none; flex-direction: column; gap: 2px; }
.ask-workspace {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 9px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  padding: 8px;
  color: var(--ask-ink-soft);
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}
.ask-workspace:hover { background: rgba(255, 255, 255, 0.62); color: #2f3949; }
.ask-workspace.active {
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 1px 2px rgba(30, 45, 70, 0.05), inset 0 0 0 1px rgba(28, 43, 68, 0.05);
  color: #243043;
}
.ws-icon {
  display: grid;
  width: 26px;
  height: 26px;
  flex: none;
  place-items: center;
  border-radius: 8px;
  background: rgba(28, 43, 68, 0.045);
  color: #64718a;
}
.ask-workspace.active .ws-icon { background: rgba(91, 107, 239, 0.12); color: #4d5ed8; }
.ws-copy { display: grid; min-width: 0; flex: 1; gap: 1px; }
.ws-copy strong { overflow: hidden; font-size: 12.5px; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }
.ws-copy small { overflow: hidden; color: var(--ask-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.ws-check { flex: none; color: #4d5ed8; }

.ask-session-list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 1px;
  overflow-y: auto;
  padding-right: 2px;
  scrollbar-color: rgba(98, 145, 184, 0.22) transparent;
  scrollbar-width: thin;
}
.ask-session {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  padding: 7px 8px;
  color: var(--ask-ink-soft);
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}
.ask-session:hover { background: rgba(255, 255, 255, 0.62); color: #2f3949; }
.ask-session.active {
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 1px 2px rgba(30, 45, 70, 0.05), inset 0 0 0 1px rgba(28, 43, 68, 0.05);
  color: #243043;
}
.ss-icon { flex: none; color: #8b96a8; }
.ask-session.active .ss-icon { color: #4d5ed8; }
.ss-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 1px; }
.ss-copy strong { overflow: hidden; font-size: 12px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.ss-copy small { color: var(--ask-muted); font-size: 10px; }
.ss-del {
  display: grid;
  width: 20px;
  height: 20px;
  flex: none;
  place-items: center;
  border-radius: 6px;
  color: #98a2b3;
  font-size: 10px;
  white-space: nowrap;
  opacity: 0;
  cursor: pointer;
  transition: opacity 0.18s ease, background 0.18s ease, color 0.18s ease;
}
.ask-session:hover .ss-del,
.ask-session.active .ss-del,
.ss-del:focus-visible { opacity: 1; }
.ss-del:hover { background: rgba(196, 66, 75, 0.12); color: #c4424b; }
.ss-del.confirming {
  width: auto;
  padding: 0 6px;
  background: rgba(196, 66, 75, 0.14);
  color: #c4424b;
  opacity: 1;
}
.ss-del.busy { opacity: 1; }
.ss-spin { animation: ask-spin 0.9s linear infinite; }
.ask-session-empty { margin: 4px 8px 8px; color: var(--ask-muted); font-size: 11px; line-height: 1.5; }

.ask-side-bottom { display: flex; flex-direction: column; gap: 2px; margin-top: auto; padding-top: 14px; }
.ask-side-link {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  padding: 8px 9px;
  color: var(--ask-ink-soft);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}
.ask-side-link:hover { background: rgba(255, 255, 255, 0.62); color: #2f3949; }
.ask-side-link.active {
  background: rgba(255, 255, 255, 0.86);
  box-shadow: inset 0 0 0 1px rgba(91, 107, 239, 0.16);
  color: #3b4dc0;
}
.ask-user { display: flex; align-items: center; gap: 9px; margin-top: 10px; padding: 8px 9px; }
.ask-avatar {
  display: grid;
  width: 26px;
  height: 26px;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(140deg, #dfe7ff, #e8e1ff);
  color: #4c5bd4;
  font-size: 11.5px;
  font-weight: 650;
}
.ask-user-copy { display: grid; min-width: 0; gap: 1px; }
.ask-user-copy strong { overflow: hidden; color: #3a4455; font-size: 12px; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }
.ask-user-copy small { overflow: hidden; color: var(--ask-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

.ask-main { position: relative; z-index: 1; display: flex; min-width: 0; flex: 1; flex-direction: column; }
.ask-top {
  position: relative;
  z-index: 30;
  display: flex;
  height: 54px;
  min-height: 54px;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.ask-live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
  padding: 5px 11px;
  box-shadow: inset 0 0 0 1px rgba(28, 43, 68, 0.05);
  color: #5f6b7e;
  font-size: 11px;
}
.ask-top-left { display: flex; align-items: center; gap: 10px; }
.ask-side-toggle {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #68748a;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}
.ask-side-toggle:hover { background: rgba(255, 255, 255, 0.72); color: #2f3949; }
.ask-live i { width: 5px; height: 5px; border-radius: 50%; background: #37b58f; box-shadow: 0 0 6px rgba(55, 181, 143, 0.8); }
.ask-live.temp i { background: #d69a3c; box-shadow: 0 0 6px rgba(214, 154, 60, 0.8); }
.ask-top-actions { display: flex; align-items: center; gap: 10px; }
.ask-model-state { color: #7c8798; font-size: 11px; }
.ask-theme {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #68748a;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}
.ask-theme:hover { background: rgba(255, 255, 255, 0.72); color: #2f3949; }
.ask-wallpaper-wrap { position: relative; }
.ask-wallpaper-btn {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #7c8798;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}
.ask-wallpaper-btn:hover,
.ask-wallpaper-btn.active { background: rgba(255, 255, 255, 0.72); color: #2f3949; }
.ask-wallpaper-pop {
  position: absolute;
  z-index: 21;
  top: calc(100% + 12px);
  right: -8px;
  width: 280px;
  border: 1px solid rgba(28, 43, 68, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 18px 40px rgba(23, 36, 84, 0.16);
  padding: 13px;
}
.wp-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; }
.wp-head strong { flex: none; color: #2b3444; font-size: 12.5px; white-space: nowrap; }
.wp-head span { min-width: 0; flex: 1; overflow: hidden; color: #8b96a8; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.wp-preview {
  display: grid;
  height: 120px;
  place-items: center;
  overflow: hidden;
  border-radius: 10px;
  background: linear-gradient(145deg, #eef3fb, #e7eef9);
  color: #93a0b3;
  font-size: 10.5px;
}
.wp-preview img,
.wp-preview video { width: 100%; height: 100%; object-fit: cover; }
.wp-actions { display: flex; gap: 8px; margin-top: 10px; }
.wp-primary {
  display: inline-flex;
  height: 30px;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 0;
  border-radius: 8px;
  background: #3f6df0;
  color: #fff;
  font-size: 11.5px;
  cursor: pointer;
}
.wp-primary:disabled { opacity: 0.6; cursor: default; }
.wp-ghost {
  height: 30px;
  border: 1px solid rgba(28, 43, 68, 0.12);
  border-radius: 8px;
  background: transparent;
  color: #5c6879;
  font-size: 11.5px;
  cursor: pointer;
  padding: 0 10px;
}
.wp-ghost:disabled { opacity: 0.45; cursor: default; }
.wp-hint { margin: 8px 0 0; color: #8b96a8; font-size: 9.5px; line-height: 1.5; }
.wp-error { margin: 6px 0 0; color: #c4424b; font-size: 10px; }
.ask-ghost {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  padding: 6px 9px;
  color: #5b677a;
  font-size: 12px;
  cursor: pointer;
}
.ask-ghost:hover { background: rgba(255, 255, 255, 0.6); color: #2f3949; }

.ask-body {
  position: relative;
  z-index: 1;
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 24px 34px;
}
.ask-body.has-thread { justify-content: flex-start; padding-bottom: 16px; }
.ask-thread {
  width: 100%;
  flex: 1;
  overflow: auto;
  overscroll-behavior: contain;
  padding: 8px 4px 6px;
  scrollbar-color: rgba(60, 80, 110, 0.22) transparent;
  scrollbar-width: thin;
}
.ask-thread-inner { display: flex; width: min(820px, 100%); margin: 0 auto; flex-direction: column; gap: 14px; }

.ask-hero { margin-bottom: 26px; text-align: center; animation: ask-rise 0.45s ease both; }
.ask-hero h1 { margin: 0; color: #232c3b; font-size: clamp(25px, 3.1vw, 34px); font-weight: 600; letter-spacing: -0.6px; }
.ask-hero h1 em {
  background: linear-gradient(100deg, #5b6bef 0%, #7c6cf5 55%, #4f9ad8 100%);
  background-clip: text;
  color: transparent;
  font-style: normal;
  -webkit-background-clip: text;
}
.ask-hero p { margin: 12px 0 0; color: #7b8698; font-size: 13px; }

.ask-dock { width: min(780px, 100%); flex: none; }
.ask-modes {
  display: flex;
  width: max-content;
  margin: 0 auto 12px;
  gap: 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  padding: 3px;
  box-shadow: inset 0 0 0 1px rgba(28, 43, 68, 0.04);
  backdrop-filter: blur(18px);
}
.ask-modes button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  padding: 6px 13px;
  color: #7b8698;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}
.ask-modes button:hover { color: #4a5568; }
.ask-modes button.active { background: #fff; box-shadow: 0 2px 8px rgba(31, 47, 74, 0.09); color: #33405c; }

.ask-composer {
  position: relative;
  z-index: 25;
  border: 1px solid rgba(255, 255, 255, 0.95);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  padding: 15px 16px 10px;
  box-shadow: 0 24px 60px rgba(31, 47, 74, 0.12), 0 2px 6px rgba(31, 47, 74, 0.04), inset 0 0 0 1px rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(30px) saturate(150%);
  -webkit-backdrop-filter: blur(30px) saturate(150%);
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}
.ask-composer:focus-within {
  border-color: rgba(120, 140, 255, 0.45);
  box-shadow: 0 26px 66px rgba(31, 47, 74, 0.14), 0 0 0 4px rgba(120, 140, 255, 0.08);
}
.ask-composer textarea {
  width: 100%;
  min-height: 46px;
  max-height: 180px;
  border: 0;
  background: transparent;
  padding: 2px 4px;
  color: #2f3a4d;
  font-size: 14px;
  line-height: 1.7;
  outline: none;
  resize: none;
}
.ask-composer textarea::placeholder { color: #9aa5b6; }
.ask-composer-foot { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.ask-menu-wrap { position: relative; display: flex; min-width: 0; }
.ask-menu-wrap.model { margin-left: auto; }
.ask-pill {
  display: inline-flex;
  max-width: 300px;
  min-width: 0;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(28, 43, 68, 0.06);
  border-radius: 999px;
  background: rgba(244, 247, 252, 0.9);
  padding: 6px 10px;
  color: #59657a;
  font-size: 11.5px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}
.pill-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pill-caret { flex: none; }
.ask-pill:hover,
.ask-pill.open { border-color: rgba(91, 107, 239, 0.25); background: #fff; color: #3d4c6d; }
.ask-send {
  display: grid;
  width: 34px;
  height: 34px;
  flex: none;
  place-items: center;
  border: 1px solid rgba(28, 43, 68, 0.08);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 2px 8px rgba(31, 47, 74, 0.06);
  color: #3a4455;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, color 0.2s ease, opacity 0.2s ease, transform 0.2s ease;
}
.ask-send:hover:not(:disabled) {
  border-color: rgba(91, 107, 239, 0.3);
  background: #fff;
  box-shadow: 0 8px 18px rgba(31, 47, 74, 0.1);
  color: #3b4dc0;
  transform: translateY(-1px);
}
.ask-send:disabled { opacity: 0.45; cursor: not-allowed; }
.ask-composer-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
  color: #9aa5b6;
  font-size: 10.5px;
}
.ask-composer-note span { display: inline-flex; align-items: center; gap: 5px; }

.ask-pop {
  position: absolute;
  z-index: 40;
  bottom: calc(100% + 10px);
  width: 268px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.94);
  padding: 6px;
  box-shadow: 0 20px 50px rgba(31, 47, 74, 0.16), 0 1px 3px rgba(31, 47, 74, 0.05);
  animation: ask-pop 0.16s ease both;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
}
.ask-pop.left { left: 0; }
.ask-pop.right { right: 0; }
.ask-pop-label { padding: 7px 10px 5px; color: #98a3b4; font-size: 10px; letter-spacing: 0.4px; }
.ask-pop-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 9px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  padding: 8px 10px;
  color: #4a566a;
  text-align: left;
  cursor: pointer;
}
.ask-pop-item:hover { background: #f2f5fa; }
.ask-pop-item.active { color: #3f4fd0; }
.ask-pop-item:disabled { opacity: 0.6; cursor: default; }
.ask-pop-item.action { margin-top: 4px; border-top: 1px solid rgba(28, 43, 68, 0.05); border-radius: 0 0 9px 9px; color: #5c6879; }
.pop-copy { display: grid; min-width: 0; flex: 1; gap: 1px; }
.pop-copy strong { overflow: hidden; font-size: 12px; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }
.pop-copy small { overflow: hidden; color: #98a3b4; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.ask-pop-empty { padding: 10px; color: #98a3b4; font-size: 11.5px; }
.ask-pop-backdrop { position: fixed; z-index: 20; inset: 0; }

.ask-bubble {
  align-self: flex-end;
  max-width: 76%;
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 16px 16px 5px 16px;
  background: rgba(255, 255, 255, 0.86);
  padding: 11px 15px;
  box-shadow: 0 6px 18px rgba(31, 47, 74, 0.06);
  color: #33405a;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.ask-answer {
  --workspace-text: #2f3a4d;
  --workspace-text-muted: #6b778c;
  --workspace-text-subtle: #93a0b4;
  --workspace-border: rgba(31, 47, 74, 0.1);
  --workspace-focus: #4f63d8;
  --workspace-surface-inset: rgba(240, 244, 251, 0.9);
  --workspace-code-background: #f4f7fd;
  --workspace-code-border: #e1e8f4;
  --workspace-code-text: #33405a;
  --workspace-table-header: #f5f8fe;
  --workspace-radius: 8px;
  align-self: stretch;
  border: 1px solid rgba(255, 255, 255, 0.92);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.76);
  padding: 15px 18px 16px;
  box-shadow: 0 12px 34px rgba(31, 47, 74, 0.07);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}
.ask-answer-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  color: #5b6bef;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2px;
}
.ask-answer-label em {
  margin-left: auto;
  border-radius: 999px;
  background: rgba(91, 107, 239, 0.09);
  padding: 2px 8px;
  color: #6572c9;
  font-size: 10px;
  font-style: normal;
  font-weight: 500;
}
.ask-thinking { display: flex; align-items: center; gap: 5px; color: #8a95a8; font-size: 12px; }
.ask-thinking i { width: 5px; height: 5px; border-radius: 50%; background: #9aa8e8; animation: ask-blink 1.2s infinite ease-in-out; }
.ask-thinking i:nth-child(2) { animation-delay: 0.18s; }
.ask-thinking i:nth-child(3) { animation-delay: 0.36s; }
.ask-thinking span { margin-left: 6px; }
.ask-error { margin: 10px 2px 0; color: #b25454; font-size: 11.5px; }
.ask-hint { margin: 10px 2px 0; color: #8b96a8; font-size: 11.5px; }
.ask-hint button {
  border: 0;
  background: transparent;
  color: #4f5fd8;
  font-size: 11.5px;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}
.ask-spin { animation: ask-spin 0.9s linear infinite; }

.ask-toast {
  position: fixed;
  top: 66px;
  left: 50%;
  z-index: 60;
  transform: translateX(-50%);
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  padding: 9px 16px;
  box-shadow: 0 14px 34px rgba(31, 47, 74, 0.14);
  color: #3a4455;
  font-size: 12px;
  white-space: nowrap;
  backdrop-filter: blur(18px);
  pointer-events: none;
}
.ask-toast-enter-active, .ask-toast-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.ask-toast-enter-from, .ask-toast-leave-to { opacity: 0; transform: translate(-50%, -6px); }

@keyframes ask-rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes ask-pop {
  from { opacity: 0; transform: translateY(4px) scale(0.99); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes ask-blink {
  0%, 80%, 100% { opacity: 0.35; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-2px); }
}
@keyframes ask-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .ask-hero, .ask-pop { animation: none; }
  .ask-thinking i { animation: none; }
}
@media (max-width: 920px) {
  .ask-side { width: 68px; min-width: 68px; padding: 16px 8px 12px; align-items: center; }
  .brand-copy, .ask-side-head > span, .ws-copy, .ws-check, .ss-copy, .ask-side-link > span, .ask-user-copy { display: none; }
  .ask-brand { justify-content: center; }
  .ask-new { width: 40px; padding: 0; }
  .ask-new > span { display: none; }
  .ask-side-head { justify-content: center; margin: 18px 0 8px; }
  .ask-workspace { width: 44px; justify-content: center; padding: 8px 0; }
  .ask-session { width: 44px; justify-content: center; padding: 8px 0; }
  .ask-session-empty, .ss-del { display: none; }
  .ask-session-list { align-items: center; }
  .ask-side-link { width: 44px; justify-content: center; padding: 9px 0; }
  .ask-user { padding: 8px 0; }
}
@media (max-width: 720px) {
  .ask-top { padding: 0 14px; }
  .ask-body { padding: 0 14px 18px; }
  .ask-hero h1 { font-size: 24px; }
  .ask-pill { max-width: 150px; }
  .ask-composer-note span:last-child { display: none; }
}

/* 深色主题：跟随全局日间/夜间切换，只覆盖颜色与阴影，不改布局、尺寸与交互。 */
.ask-studio.is-dark {
  --ask-ink: #e6eaf2;
  --ask-ink-soft: #a8b2c2;
  --ask-muted: #798496;
  --ask-line: rgba(255, 255, 255, 0.08);
  background: #0b0f16;
}
.ask-studio.is-dark .ask-wallpaper {
  background:
    radial-gradient(1200px 700px at 12% -10%, #111b2e 0%, transparent 60%),
    radial-gradient(900px 600px at 92% 8%, #191331 0%, transparent 55%),
    radial-gradient(900px 700px at 60% 110%, #0d1c25 0%, transparent 55%),
    linear-gradient(150deg, #0a0e14 0%, #0c1119 48%, #090d13 100%);
}
.ask-studio.is-dark .wall-glow { opacity: 0.38; }
.ask-studio.is-dark .glow-a { background: #1b2745; }
.ask-studio.is-dark .glow-b { background: #221a3a; }
.ask-studio.is-dark .glow-c { background: #122b38; }
.ask-studio.is-dark .wall-grid {
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
}

.ask-studio.is-dark .ask-side {
  background: rgba(17, 21, 28, 0.62);
  box-shadow: 1px 0 0 rgba(255, 255, 255, 0.06), 10px 0 40px rgba(0, 0, 0, 0.34);
}
.ask-studio.is-dark .brand-copy strong { color: #e8ecf3; }
.ask-studio.is-dark .ask-new {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.06);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.28);
  color: #d3dae6;
}
.ask-studio.is-dark .ask-new:hover {
  border-color: rgba(130, 146, 255, 0.38);
  background: rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.32);
  color: #b3bdff;
}
.ask-studio.is-dark .ask-mini:hover { background: rgba(255, 255, 255, 0.08); color: #dfe5ee; }
.ask-studio.is-dark .ask-workspace:hover { background: rgba(255, 255, 255, 0.06); color: #e2e8f2; }
.ask-studio.is-dark .ask-workspace.active {
  background: rgba(130, 146, 255, 0.14);
  box-shadow: inset 0 0 0 1px rgba(130, 146, 255, 0.26);
  color: #eef1f8;
}
.ask-studio.is-dark .ws-icon { background: rgba(255, 255, 255, 0.06); color: #9aa6b8; }
.ask-studio.is-dark .ask-workspace.active .ws-icon { background: rgba(130, 146, 255, 0.22); color: #aab4ff; }
.ask-studio.is-dark .ask-session:hover { background: rgba(255, 255, 255, 0.06); color: #e2e8f2; }
.ask-studio.is-dark .ask-session.active {
  background: rgba(130, 146, 255, 0.14);
  box-shadow: inset 0 0 0 1px rgba(130, 146, 255, 0.26);
  color: #eef1f8;
}
.ask-studio.is-dark .ss-icon { color: #8b95a5; }
.ask-studio.is-dark .ask-session.active .ss-icon { color: #aab4ff; }
.ask-studio.is-dark .ss-del { color: #8b95a5; }
.ask-studio.is-dark .ss-del:hover { background: rgba(240, 138, 147, 0.16); color: #f08a93; }
.ask-studio.is-dark .ss-del.confirming { background: rgba(240, 138, 147, 0.2); color: #f08a93; }
.ask-studio.is-dark .ws-check { color: #aab4ff; }
.ask-studio.is-dark .ask-side-link:hover { background: rgba(255, 255, 255, 0.06); color: #e2e8f2; }
.ask-studio.is-dark .ask-side-link.active {
  background: rgba(130, 146, 255, 0.16);
  box-shadow: inset 0 0 0 1px rgba(130, 146, 255, 0.3);
  color: #b7c0ff;
}
.ask-studio.is-dark .ask-avatar {
  background: linear-gradient(140deg, #2a3350, #33294e);
  color: #c3cbff;
}
.ask-studio.is-dark .ask-user-copy strong { color: #d7dee9; }

.ask-studio.is-dark .ask-live {
  background: rgba(255, 255, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
  color: #a9b4c6;
}
.ask-studio.is-dark .ask-side-toggle { color: #98a4b6; }
.ask-studio.is-dark .ask-side-toggle:hover { background: rgba(255, 255, 255, 0.07); color: #e6ebf3; }
.ask-studio.is-dark .ask-model-state { color: #8b95a5; }
.ask-studio.is-dark .ask-theme { color: #98a4b6; }
.ask-studio.is-dark .ask-theme:hover { background: rgba(255, 255, 255, 0.07); color: #e6ebf3; }
.ask-studio.is-dark .ask-wallpaper-btn { color: #98a4b6; }
.ask-studio.is-dark .ask-wallpaper-btn:hover,
.ask-studio.is-dark .ask-wallpaper-btn.active { background: rgba(255, 255, 255, 0.07); color: #e6ebf3; }
.ask-studio.is-dark .ask-wallpaper-pop {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(17, 26, 39, 0.97);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.5);
}
.ask-studio.is-dark .wp-head strong { color: #e6ebf3; }
.ask-studio.is-dark .wp-head span { color: #8b95a5; }
.ask-studio.is-dark .wp-preview { background: rgba(255, 255, 255, 0.04); color: #8b95a5; }
.ask-studio.is-dark .wp-ghost { border-color: rgba(255, 255, 255, 0.14); color: #b8c2d2; }
.ask-studio.is-dark .wp-hint { color: #8b95a5; }
.ask-studio.is-dark .wp-error { color: #f08a93; }
.ask-studio.is-dark .ask-ghost { color: #a8b2c2; }
.ask-studio.is-dark .ask-ghost:hover { background: rgba(255, 255, 255, 0.07); color: #e6ebf3; }

.ask-studio.is-dark .ask-thread { scrollbar-color: rgba(255, 255, 255, 0.18) transparent; }
.ask-studio.is-dark .ask-hero h1 { color: #edf0f6; }
.ask-studio.is-dark .ask-hero h1 em {
  background: linear-gradient(100deg, #8b97ff 0%, #b39cff 55%, #7cc3f0 100%);
  background-clip: text;
  -webkit-background-clip: text;
}
.ask-studio.is-dark .ask-hero p { color: #9aa5b6; }

.ask-studio.is-dark .ask-modes {
  background: rgba(255, 255, 255, 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.ask-studio.is-dark .ask-modes button { color: #9aa5b6; }
.ask-studio.is-dark .ask-modes button:hover { color: #c8d0dd; }
.ask-studio.is-dark .ask-modes button.active {
  background: rgba(255, 255, 255, 0.12);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
  color: #eef1f7;
}

.ask-studio.is-dark .ask-composer {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(22, 27, 36, 0.72);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45), 0 2px 6px rgba(0, 0, 0, 0.3), inset 0 0 0 1px rgba(255, 255, 255, 0.05);
}
.ask-studio.is-dark .ask-composer:focus-within {
  border-color: rgba(130, 146, 255, 0.5);
  box-shadow: 0 26px 66px rgba(0, 0, 0, 0.5), 0 0 0 4px rgba(130, 146, 255, 0.12);
}
.ask-studio.is-dark .ask-composer textarea { color: #e3e8f0; }
.ask-studio.is-dark .ask-composer textarea::placeholder { color: #6f7a8b; }
.ask-studio.is-dark .ask-pill {
  border-color: rgba(255, 255, 255, 0.09);
  background: rgba(255, 255, 255, 0.06);
  color: #aab4c4;
}
.ask-studio.is-dark .ask-pill:hover,
.ask-studio.is-dark .ask-pill.open {
  border-color: rgba(130, 146, 255, 0.4);
  background: rgba(255, 255, 255, 0.12);
  color: #eef1f7;
}
.ask-studio.is-dark .ask-send {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  color: #e3e8f0;
}
.ask-studio.is-dark .ask-send:hover:not(:disabled) {
  border-color: rgba(130, 146, 255, 0.45);
  background: rgba(130, 146, 255, 0.22);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.36);
  color: #fff;
}
.ask-studio.is-dark .ask-composer-note { color: #78849a; }

.ask-studio.is-dark .ask-pop {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(22, 27, 36, 0.96);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5), 0 1px 3px rgba(0, 0, 0, 0.4);
}
.ask-studio.is-dark .ask-pop-label,
.ask-studio.is-dark .pop-copy small,
.ask-studio.is-dark .ask-pop-empty { color: #7f8a9b; }
.ask-studio.is-dark .ask-pop-item { color: #c3ccda; }
.ask-studio.is-dark .ask-pop-item:hover { background: rgba(255, 255, 255, 0.07); }
.ask-studio.is-dark .ask-pop-item.active { color: #aab4ff; }
.ask-studio.is-dark .ask-pop-item.action {
  border-top-color: rgba(255, 255, 255, 0.08);
  color: #9aa5b6;
}

.ask-studio.is-dark .ask-bubble {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(130, 146, 255, 0.16);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
  color: #e6eaf4;
}
.ask-studio.is-dark .ask-answer {
  --workspace-text: #e6eaf2;
  --workspace-text-muted: #9aa5b6;
  --workspace-text-subtle: #75808f;
  --workspace-border: rgba(255, 255, 255, 0.1);
  --workspace-focus: #9aa7ff;
  --workspace-surface-inset: rgba(255, 255, 255, 0.06);
  --workspace-code-background: #0d1118;
  --workspace-code-border: #242b38;
  --workspace-code-text: #d9e0ea;
  --workspace-table-header: #151a23;
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(19, 23, 31, 0.72);
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.35);
}
.ask-studio.is-dark .ask-answer-label { color: #8f9bff; }
.ask-studio.is-dark .ask-answer-label em {
  background: rgba(130, 146, 255, 0.16);
  color: #b3bcff;
}
.ask-studio.is-dark .ask-thinking { color: #8b95a5; }
.ask-studio.is-dark .ask-thinking i { background: #6f7fd0; }
.ask-studio.is-dark .ask-error { color: #e08a8a; }
.ask-studio.is-dark .ask-hint { color: #8b95a5; }
.ask-studio.is-dark .ask-hint button { color: #9aa7ff; }

.ask-studio.is-dark .ask-toast {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(22, 27, 36, 0.94);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.46);
  color: #e3e8f0;
}
</style>

<style>
.app-shell:has(.ask-studio) { height: 100dvh; min-height: 600px; overflow: hidden; background: #eef3fa; }
.app-shell:has(.ask-studio.is-dark) { background: #080b11; }
.app-shell:has(.ask-studio) > .app-topbar { display: none; }
.app-shell:has(.ask-studio) > .app-content { height: 100%; }
</style>
