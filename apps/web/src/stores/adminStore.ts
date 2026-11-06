import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  adminLogin,
  getAdminOverview,
  listAdminEnterprises,
  listAdminUsers,
  resetAdminUserPassword,
  updateAdminUserStatus,
} from "@/api/admin";
import type {
  AdminEnterpriseRow,
  AdminOverview,
  AdminUserPage,
  AdminUserRow,
} from "@/api/admin";
import { clearAdminSession, readAdminSession, writeAdminSession } from "@/lib/adminStorage";

function sessionExpired(expiresAt: string | null): boolean {
  if (!expiresAt) {
    return false;
  }
  const timestamp = Date.parse(expiresAt);
  return Number.isFinite(timestamp) && timestamp <= Date.now();
}

export const useAdminStore = defineStore("admin", () => {
  const stored = readAdminSession();
  const token = ref<string | null>(
    stored && !sessionExpired(stored.expiresAt) ? stored.token : null,
  );
  const expiresAt = ref<string | null>(stored?.expiresAt ?? null);
  const overview = ref<AdminOverview | null>(null);
  const enterprises = ref<AdminEnterpriseRow[]>([]);
  const users = ref<AdminUserRow[]>([]);
  const userTotal = ref(0);
  const userPage = ref(1);
  const userPageSize = 10;
  const loading = ref(false);
  const error = ref<string | null>(null);

  const isAuthenticated = computed(() => token.value !== null);
  const activeUsers = computed(() => overview.value?.active_user_count ?? 0);

  function persist(): void {
    if (token.value === null) {
      clearAdminSession();
      return;
    }
    writeAdminSession({ token: token.value, expiresAt: expiresAt.value });
  }

  async function login(username: string, password: string): Promise<void> {
    const session = await adminLogin(username, password);
    token.value = session.token;
    expiresAt.value = session.expires_at;
    persist();
  }

  function clear(): void {
    token.value = null;
    expiresAt.value = null;
    overview.value = null;
    enterprises.value = [];
    users.value = [];
    userTotal.value = 0;
    userPage.value = 1;
    clearAdminSession();
  }

  function logout(): void {
    clear();
  }

  async function loadOverview(): Promise<void> {
    if (token.value === null) return;
    overview.value = await getAdminOverview(token.value);
  }

  async function loadEnterprises(q?: string): Promise<void> {
    if (token.value === null) return;
    const result = await listAdminEnterprises(token.value, q);
    enterprises.value = result.items;
  }

  async function loadUsers(
    options: { page?: number; q?: string; enterpriseId?: string } = {},
  ): Promise<void> {
    if (token.value === null) return;
    const result: AdminUserPage = await listAdminUsers(token.value, {
      page: options.page ?? userPage.value,
      pageSize: userPageSize,
      q: options.q,
      enterpriseId: options.enterpriseId,
    });
    users.value = result.items;
    userTotal.value = result.total;
    userPage.value = result.page;
  }

  async function refresh(): Promise<void> {
    if (token.value === null) return;
    loading.value = true;
    error.value = null;
    try {
      await Promise.all([loadOverview(), loadEnterprises(), loadUsers()]);
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : "管理台数据加载失败";
      if (error.value.includes("登录状态") || error.value.includes("AUTH")) {
        clear();
      }
    } finally {
      loading.value = false;
    }
  }

  async function setUserStatus(userId: string, status: "active" | "disabled"): Promise<void> {
    if (token.value === null) return;
    const updated = await updateAdminUserStatus(token.value, userId, status);
    users.value = users.value.map((item) => (item.id === updated.id ? updated : item));
    await loadOverview();
    await loadEnterprises();
  }

  async function resetPassword(userId: string, password: string): Promise<void> {
    if (token.value === null) return;
    await resetAdminUserPassword(token.value, userId, password);
  }

  return {
    token,
    expiresAt,
    overview,
    enterprises,
    users,
    userTotal,
    userPage,
    userPageSize,
    loading,
    error,
    isAuthenticated,
    activeUsers,
    login,
    logout,
    clear,
    refresh,
    loadUsers,
    setUserStatus,
    resetPassword,
  };
});
