import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import type { AuthSession } from "@/api/auth";

const api = vi.hoisted(() => ({
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  registerEmployee: vi.fn(),
  registerEnterprise: vi.fn(),
}));

vi.mock("@/api/auth", () => api);

import { clearAuthSession, readAuthSession } from "@/lib/authStorage";
import { useAuthStore } from "./authStore";

function session(overrides: Partial<AuthSession> = {}): AuthSession {
  return {
    token: "token_admin",
    token_type: "bearer",
    expires_at: "2026-11-12T00:00:00Z",
    user: {
      id: "user_admin",
      username: "zhixi_admin",
      display_name: "叶锦豪",
      role: "enterprise_admin",
      created_at: "2026-11-05T00:00:00Z",
    },
    enterprise: {
      code: "ZX-ABC123",
      name: "智析测试科技有限公司",
      industry: null,
      company_size: null,
    },
    ...overrides,
  };
}

describe("authStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    clearAuthSession();
    vi.clearAllMocks();
  });

  it("stores the enterprise session after admin registration", async () => {
    api.registerEnterprise.mockResolvedValue(session());
    const store = useAuthStore();

    await store.registerEnterprise({
      company_name: "智析测试科技有限公司",
      industry: null,
      company_size: null,
      contact_name: "叶锦豪",
      contact_phone: "13800000000",
      contact_email: null,
      username: "zhixi_admin",
      display_name: "叶锦豪",
      password: "AdminPass123",
    });

    expect(store.isAuthenticated).toBe(true);
    expect(store.user?.role).toBe("enterprise_admin");
    expect(store.roleLabel).toBe("企业管理员");
    expect(readAuthSession()?.enterprise.code).toBe("ZX-ABC123");
  });

  it("clears the local session on logout", async () => {
    api.login.mockResolvedValue(session());
    api.logout.mockResolvedValue({ logged_out: true });
    const store = useAuthStore();

    await store.login({ username: "zhixi_admin", password: "AdminPass123" });
    expect(readAuthSession()).not.toBeNull();

    await store.logout();

    expect(store.isAuthenticated).toBe(false);
    expect(store.user).toBeNull();
    expect(readAuthSession()).toBeNull();
    expect(api.logout).toHaveBeenCalledWith("token_admin");
  });

  it("refreshes the persisted profile with the server copy", async () => {
    api.login.mockResolvedValue(session());
    api.getMe.mockResolvedValue({
      user: { ...session().user, display_name: "更新后的姓名" },
      enterprise: session().enterprise,
    });
    const store = useAuthStore();

    await store.login({ username: "zhixi_admin", password: "AdminPass123" });
    await store.refresh();

    expect(store.user?.display_name).toBe("更新后的姓名");
    expect(readAuthSession()?.user.display_name).toBe("更新后的姓名");
  });
});
