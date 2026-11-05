import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  getMe,
  login as loginRequest,
  logout as logoutRequest,
  registerEmployee as registerEmployeeRequest,
  registerEnterprise as registerEnterpriseRequest,
} from "@/api/auth";
import type {
  AuthEnterprise,
  AuthSession,
  AuthUser,
  EmployeeRegisterPayload,
  EnterpriseRegisterPayload,
  LoginPayload,
} from "@/api/auth";
import { clearAuthSession, readAuthSession, writeAuthSession } from "@/lib/authStorage";

export const useAuthStore = defineStore("auth", () => {
  const stored = readAuthSession();
  const token = ref<string | null>(stored?.token ?? null);
  const user = ref<AuthUser | null>(stored?.user ?? null);
  const enterprise = ref<AuthEnterprise | null>(stored?.enterprise ?? null);
  const expiresAt = ref<string | null>(stored?.expiresAt ?? null);

  const isAuthenticated = computed(() => token.value !== null);
  const roleLabel = computed(() => {
    if (user.value?.role === "enterprise_admin") return "企业管理员";
    if (user.value?.role === "employee") return "企业职工";
    return "未登录";
  });
  const avatarText = computed(() => {
    const name = user.value?.display_name?.trim();
    return name ? name.slice(0, 1).toUpperCase() : "?";
  });

  function persist(): void {
    if (token.value === null || user.value === null || enterprise.value === null) {
      clearAuthSession();
      return;
    }
    writeAuthSession({
      token: token.value,
      user: user.value,
      enterprise: enterprise.value,
      expiresAt: expiresAt.value,
    });
  }

  function applySession(session: AuthSession): void {
    token.value = session.token;
    user.value = session.user;
    enterprise.value = session.enterprise;
    expiresAt.value = session.expires_at;
    persist();
  }

  function clearSession(): void {
    token.value = null;
    user.value = null;
    enterprise.value = null;
    expiresAt.value = null;
    clearAuthSession();
  }

  async function login(payload: LoginPayload): Promise<void> {
    applySession(await loginRequest(payload));
  }

  async function registerEnterprise(payload: EnterpriseRegisterPayload): Promise<AuthSession> {
    const session = await registerEnterpriseRequest(payload);
    applySession(session);
    return session;
  }

  async function registerEmployee(payload: EmployeeRegisterPayload): Promise<AuthSession> {
    const session = await registerEmployeeRequest(payload);
    applySession(session);
    return session;
  }

  async function refresh(): Promise<void> {
    if (token.value === null) {
      return;
    }
    try {
      const profile = await getMe();
      user.value = profile.user;
      enterprise.value = profile.enterprise;
      persist();
    } catch {
      clearSession();
    }
  }

  async function logout(): Promise<void> {
    const currentToken = token.value;
    clearSession();
    if (currentToken === null) {
      return;
    }
    try {
      await logoutRequest(currentToken);
    } catch {
      // 本地会话已清除；服务端撤销失败不阻塞退出。
    }
  }

  return {
    token,
    user,
    enterprise,
    expiresAt,
    isAuthenticated,
    roleLabel,
    avatarText,
    login,
    registerEnterprise,
    registerEmployee,
    refresh,
    logout,
    clearSession,
  };
});
