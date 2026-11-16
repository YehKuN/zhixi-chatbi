<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  Activity,
  Building2,
  Database,
  KeyRound,
  LoaderCircle,
  LogOut,
  Moon,
  RefreshCw,
  Search,
  ShieldCheck,
  Sun,
  Users,
  X,
  Zap,
} from "@lucide/vue";

import { ApiClientError } from "@/api/client";
import type { AdminUserRow } from "@/api/admin";
import { useTheme } from "@/lib/theme";
import { useAdminStore } from "@/stores/adminStore";

const admin = useAdminStore();
const { isDark, toggleTheme } = useTheme();

const loginForm = reactive({ username: "admin", password: "" });
const loginError = ref("");
const submitting = ref(false);

const enterpriseQuery = ref("");
const userQuery = ref("");
const enterpriseFilter = ref("");
const actionError = ref("");
const toasts = ref<{ id: number; message: string; kind: "success" | "error" }[]>([]);
let toastSeed = 0;

const resetTarget = ref<AdminUserRow | null>(null);
const resetPassword = ref("");
const resetSubmitting = ref(false);
const resetError = ref("");

const totalPages = computed(() =>
  Math.max(1, Math.ceil(admin.userTotal / admin.userPageSize)),
);
const hasMetrics = computed(() => admin.overview !== null);

function describeError(caught: unknown): string {
  if (caught instanceof ApiClientError) {
    const messages: Record<string, string> = {
      INVALID_CREDENTIALS: "管理员账号或密码错误",
      AUTH_REQUIRED: "登录状态已失效，请重新登录",
      CONFIGURATION_ERROR: "服务器尚未配置 ADMIN_PASSWORD 环境变量",
      ADMIN_ACTION_REJECTED: "该操作被拒绝：企业至少需要保留一名可用管理员",
      USERNAME_TAKEN: "用户名已存在",
      VALIDATION_ERROR: "提交内容不合法，请检查后重试",
    };
    return messages[caught.code] ?? caught.message;
  }
  if (caught instanceof Error) return caught.message;
  return "请求失败，请稍后重试";
}

function notify(message: string, kind: "success" | "error" = "success"): void {
  const id = ++toastSeed;
  toasts.value = [...toasts.value, { id, message, kind }];
  window.setTimeout(() => {
    toasts.value = toasts.value.filter((item) => item.id !== id);
  }, 3200);
}

function formatNumber(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString("zh-CN");
}

function formatTokens(value: number | null | undefined): string {
  const total = value ?? 0;
  if (total >= 1_000_000) return `${(total / 1_000_000).toFixed(2)}M`;
  if (total >= 1_000) return `${(total / 1_000).toFixed(1)}K`;
  return String(total);
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function roleLabel(role: AdminUserRow["role"]): string {
  return role === "enterprise_admin" ? "企业管理员" : "企业职工";
}

async function handleLogin(): Promise<void> {
  if (submitting.value) return;
  loginError.value = "";
  submitting.value = true;
  try {
    await admin.login(loginForm.username.trim(), loginForm.password);
    loginForm.password = "";
    await admin.refresh();
  } catch (caught) {
    loginError.value = describeError(caught);
  } finally {
    submitting.value = false;
  }
}

async function handleLogout(): Promise<void> {
  admin.logout();
  loginError.value = "";
}

async function handleRefresh(): Promise<void> {
  await admin.refresh();
  if (admin.error) {
    notify(admin.error, "error");
  } else {
    notify("管理台数据已刷新");
  }
}

async function searchEnterprises(): Promise<void> {
  try {
    await admin.refresh();
  } catch (caught) {
    notify(describeError(caught), "error");
  }
}

async function searchUsers(): Promise<void> {
  actionError.value = "";
  try {
    await admin.loadUsers({
      page: 1,
      q: userQuery.value.trim() || undefined,
      enterpriseId: enterpriseFilter.value || undefined,
    });
  } catch (caught) {
    actionError.value = describeError(caught);
  }
}

async function changePage(delta: number): Promise<void> {
  const target = admin.userPage + delta;
  if (target < 1 || target > totalPages.value) return;
  await admin.loadUsers({
    page: target,
    q: userQuery.value.trim() || undefined,
    enterpriseId: enterpriseFilter.value || undefined,
  });
}

async function toggleStatus(user: AdminUserRow): Promise<void> {
  actionError.value = "";
  const next = user.status === "active" ? "disabled" : "active";
  try {
    await admin.setUserStatus(user.id, next);
    notify(next === "disabled" ? `已停用 ${user.username}` : `已启用 ${user.username}`);
  } catch (caught) {
    actionError.value = describeError(caught);
  }
}

function openReset(user: AdminUserRow): void {
  resetTarget.value = user;
  resetPassword.value = "";
  resetError.value = "";
}

function closeReset(): void {
  if (resetSubmitting.value) return;
  resetTarget.value = null;
  resetPassword.value = "";
  resetError.value = "";
}

async function submitReset(): Promise<void> {
  if (resetTarget.value === null || resetSubmitting.value) return;
  if (resetPassword.value.length < 8) {
    resetError.value = "新密码至少 8 位";
    return;
  }
  resetSubmitting.value = true;
  resetError.value = "";
  try {
    await admin.resetPassword(resetTarget.value.id, resetPassword.value);
    notify(`已重置 ${resetTarget.value.username} 的密码，该账号现有会话已失效`);
    closeReset();
  } catch (caught) {
    resetError.value = describeError(caught);
  } finally {
    resetSubmitting.value = false;
  }
}

onMounted(async () => {
  if (admin.isAuthenticated) {
    await admin.refresh();
  }
});
</script>

<template>
  <section class="admin-page">
    <div class="admin-aurora" aria-hidden="true" />

    <div v-if="!admin.isAuthenticated" class="admin-login-shell">
      <form class="admin-login-card" @submit.prevent="handleLogin">
        <button
          type="button"
          class="admin-login-theme"
          :title="isDark ? '切换日间模式' : '切换夜间模式'"
          :aria-label="isDark ? '切换日间模式' : '切换夜间模式'"
          @click="toggleTheme"
        >
          <Sun v-if="isDark" :size="15" />
          <Moon v-else :size="15" />
        </button>
        <div class="admin-login-brand">
          <img src="/chatbi-mark.svg" alt="" aria-hidden="true" />
          <div>
            <strong>智析 ChatBI</strong>
            <small>PLATFORM ADMIN CONSOLE</small>
          </div>
        </div>
        <h1>平台管理台</h1>
        <p>仅限运营者访问。管理员凭据只从服务器环境变量读取，与入驻企业账号隔离。</p>

        <label class="admin-field">
          <span>管理员账号</span>
          <input v-model="loginForm.username" type="text" autocomplete="username" required />
        </label>
        <label class="admin-field">
          <span>管理员密码</span>
          <input
            v-model="loginForm.password"
            type="password"
            autocomplete="current-password"
            placeholder="由 ADMIN_PASSWORD 环境变量提供"
            required
          />
        </label>

        <div v-if="loginError" class="admin-alert">{{ loginError }}</div>

        <button type="submit" class="admin-primary" :disabled="submitting">
          <LoaderCircle v-if="submitting" :size="16" class="adm-spin" />
          <ShieldCheck v-else :size="16" />
          <span>{{ submitting ? "验证中…" : "进入管理台" }}</span>
        </button>

        <small class="admin-login-foot">令牌有效期 12 小时，关闭标签页即退出</small>
        <RouterLink class="admin-back-login" to="/login">← 返回企业登录</RouterLink>
      </form>
    </div>

    <template v-else>
      <header class="admin-topbar">
        <div class="admin-brand">
          <img src="/chatbi-mark.svg" alt="" aria-hidden="true" />
          <div>
            <strong>智析 ChatBI · 平台管理台</strong>
            <small>企业入驻 / 账号治理 / Token 用量</small>
          </div>
        </div>
        <div class="admin-topbar-actions">
          <span class="admin-live"><i />服务在线</span>
          <button type="button" class="admin-ghost" :disabled="admin.loading" @click="handleRefresh">
            <RefreshCw :size="14" :class="{ 'adm-spin': admin.loading }" />
            刷新
          </button>
          <button
            type="button"
            class="admin-ghost"
            :title="isDark ? '切换日间模式' : '切换夜间模式'"
            :aria-label="isDark ? '切换日间模式' : '切换夜间模式'"
            @click="toggleTheme"
          >
            <Sun v-if="isDark" :size="14" />
            <Moon v-else :size="14" />
          </button>
          <RouterLink class="admin-ghost" to="/login">返回企业登录</RouterLink>
          <button type="button" class="admin-ghost danger" @click="handleLogout">
            <LogOut :size="14" />
            退出
          </button>
        </div>
      </header>

      <main class="admin-content">
        <section class="admin-kpis">
          <article class="admin-kpi">
            <span class="admin-kpi-icon"><Building2 :size="17" /></span>
            <div>
              <small>入驻企业</small>
              <strong>{{ formatNumber(admin.overview?.enterprise_count) }}</strong>
              <em>其中 {{ formatNumber(admin.overview?.active_enterprise_count) }} 家正常</em>
            </div>
          </article>
          <article class="admin-kpi">
            <span class="admin-kpi-icon violet"><Users :size="17" /></span>
            <div>
              <small>用户账号</small>
              <strong>{{ formatNumber(admin.overview?.user_count) }}</strong>
              <em>活跃 {{ formatNumber(admin.activeUsers) }} 个</em>
            </div>
          </article>
          <article class="admin-kpi">
            <span class="admin-kpi-icon green"><Database :size="17" /></span>
            <div>
              <small>数据源</small>
              <strong>{{ formatNumber(admin.overview?.datasource_count) }}</strong>
              <em>会话 {{ formatNumber(admin.overview?.session_count) }} 个</em>
            </div>
          </article>
          <article class="admin-kpi">
            <span class="admin-kpi-icon amber"><Activity :size="17" /></span>
            <div>
              <small>分析次数</small>
              <strong>{{ formatNumber(admin.overview?.run_count) }}</strong>
              <em>已统计 Token 的 Run {{ formatNumber(admin.overview?.tracked_usage_runs) }} 个</em>
            </div>
          </article>
          <article class="admin-kpi wide">
            <span class="admin-kpi-icon cyan"><Zap :size="17" /></span>
            <div>
              <small>累计 Token 用量</small>
              <strong>{{ formatNumber(admin.overview?.usage_total_tokens) }}</strong>
              <em>
                输入 {{ formatTokens(admin.overview?.usage_input_tokens) }} · 输出
                {{ formatTokens(admin.overview?.usage_output_tokens) }} · 近 30 天
                {{ formatTokens(admin.overview?.recent_30d_tokens) }}
              </em>
            </div>
          </article>
        </section>

        <section class="admin-panel">
          <header class="admin-panel-head">
            <div>
              <h2>企业用量与规模</h2>
              <p>按企业聚合成员、数据资产、分析次数与 Token 消耗</p>
            </div>
            <form class="admin-search" @submit.prevent="searchEnterprises">
              <Search :size="14" />
              <input v-model="enterpriseQuery" type="search" placeholder="公司名称或企业 ID" />
            </form>
          </header>

          <div v-if="!hasMetrics && admin.loading" class="admin-empty">正在加载平台数据…</div>
          <div v-else-if="admin.enterprises.length === 0" class="admin-empty">
            还没有企业入驻，或搜索条件无匹配结果
          </div>
          <div v-else class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>企业</th>
                  <th>企业 ID</th>
                  <th>成员</th>
                  <th>管理员</th>
                  <th>数据源</th>
                  <th>会话</th>
                  <th>分析次数</th>
                  <th>Token 总量</th>
                  <th>最后分析</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in admin.enterprises" :key="row.id">
                  <td>
                    <strong class="adm-strong">{{ row.name }}</strong>
                    <span class="adm-sub">{{ row.industry || "未填写行业" }}</span>
                  </td>
                  <td><code class="adm-code">{{ row.code }}</code></td>
                  <td>
                    {{ formatNumber(row.user_count) }}
                    <span class="adm-sub">活跃 {{ formatNumber(row.active_user_count) }}</span>
                  </td>
                  <td>{{ formatNumber(row.admin_count) }}</td>
                  <td>{{ formatNumber(row.datasource_count) }}</td>
                  <td>{{ formatNumber(row.session_count) }}</td>
                  <td>{{ formatNumber(row.run_count) }}</td>
                  <td>
                    <strong class="adm-token">{{ formatTokens(row.usage_total_tokens) }}</strong>
                    <span class="adm-sub">
                      {{ formatTokens(row.usage_input_tokens) }} 入 /
                      {{ formatTokens(row.usage_output_tokens) }} 出
                    </span>
                  </td>
                  <td>{{ formatDate(row.last_run_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="admin-panel">
          <header class="admin-panel-head">
            <div>
              <h2>账号管理</h2>
              <p>停用账号会立即撤销其登录会话；重置密码后需用新密码重新登录</p>
            </div>
            <div class="admin-filters">
              <select v-model="enterpriseFilter" @change="searchUsers">
                <option value="">全部企业</option>
                <option v-for="item in admin.enterprises" :key="item.id" :value="item.id">
                  {{ item.name }}
                </option>
              </select>
              <form class="admin-search" @submit.prevent="searchUsers">
                <Search :size="14" />
                <input v-model="userQuery" type="search" placeholder="用户名 / 姓名 / 企业" />
              </form>
            </div>
          </header>

          <div v-if="actionError" class="admin-alert">{{ actionError }}</div>

          <div v-if="admin.users.length === 0" class="admin-empty">没有匹配的账号</div>
          <div v-else class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>账号</th>
                  <th>姓名</th>
                  <th>所属企业</th>
                  <th>角色</th>
                  <th>状态</th>
                  <th>最近登录</th>
                  <th class="adm-right">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="user in admin.users" :key="user.id">
                  <td><code class="adm-code">{{ user.username }}</code></td>
                  <td>{{ user.display_name }}</td>
                  <td>
                    <strong class="adm-strong">{{ user.enterprise_name }}</strong>
                    <span class="adm-sub">{{ user.enterprise_code }}</span>
                  </td>
                  <td>
                    <span class="adm-tag" :class="user.role === 'enterprise_admin' ? 'violet' : ''">
                      {{ roleLabel(user.role) }}
                    </span>
                  </td>
                  <td>
                    <span class="adm-status" :class="user.status === 'active' ? 'on' : 'off'">
                      {{ user.status === "active" ? "正常" : "已停用" }}
                    </span>
                  </td>
                  <td>{{ formatDate(user.last_login_at) }}</td>
                  <td class="adm-right">
                    <button type="button" class="adm-action" @click="openReset(user)">
                      <KeyRound :size="13" />重置密码
                    </button>
                    <button
                      type="button"
                      class="adm-action"
                      :class="{ danger: user.status === 'active' }"
                      @click="toggleStatus(user)"
                    >
                      {{ user.status === "active" ? "停用" : "启用" }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <footer class="admin-pager">
            <span>
              共 {{ formatNumber(admin.userTotal) }} 个账号 · 第 {{ admin.userPage }} /
              {{ totalPages }} 页
            </span>
            <div>
              <button
                type="button"
                class="admin-ghost"
                :disabled="admin.userPage <= 1"
                @click="changePage(-1)"
              >
                上一页
              </button>
              <button
                type="button"
                class="admin-ghost"
                :disabled="admin.userPage >= totalPages"
                @click="changePage(1)"
              >
                下一页
              </button>
            </div>
          </footer>
        </section>
      </main>
    </template>

    <div v-if="resetTarget" class="admin-modal-backdrop" @click.self="closeReset">
      <div class="admin-modal">
        <header>
          <div>
            <h3>重置密码</h3>
            <p>{{ resetTarget.display_name }} · {{ resetTarget.username }}</p>
          </div>
          <button type="button" class="adm-icon" aria-label="关闭" @click="closeReset">
            <X :size="16" />
          </button>
        </header>
        <label class="admin-field">
          <span>新密码（至少 8 位）</span>
          <input
            v-model="resetPassword"
            type="password"
            autocomplete="new-password"
            placeholder="输入新密码"
          />
        </label>
        <div v-if="resetError" class="admin-alert">{{ resetError }}</div>
        <footer>
          <button type="button" class="admin-ghost" @click="closeReset">取消</button>
          <button type="button" class="admin-primary" :disabled="resetSubmitting" @click="submitReset">
            <LoaderCircle v-if="resetSubmitting" :size="15" class="adm-spin" />
            <span>{{ resetSubmitting ? "提交中…" : "确认重置" }}</span>
          </button>
        </footer>
      </div>
    </div>

    <div class="admin-toasts" aria-live="polite">
      <div v-for="toast in toasts" :key="toast.id" class="admin-toast" :class="toast.kind">
        {{ toast.message }}
      </div>
    </div>
  </section>
</template>
