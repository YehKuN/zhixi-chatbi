import { requestJson } from "./client";

export interface AdminSession {
  token: string;
  token_type: string;
  expires_at: string;
}

export interface AdminOverview {
  enterprise_count: number;
  active_enterprise_count: number;
  user_count: number;
  active_user_count: number;
  datasource_count: number;
  session_count: number;
  run_count: number;
  usage_input_tokens: number;
  usage_output_tokens: number;
  usage_total_tokens: number;
  usage_model_calls: number;
  recent_30d_tokens: number;
  tracked_usage_runs: number;
}

export interface AdminEnterpriseRow {
  id: string;
  code: string;
  name: string;
  industry: string | null;
  company_size: string | null;
  status: string;
  created_at: string;
  user_count: number;
  active_user_count: number;
  admin_count: number;
  datasource_count: number;
  session_count: number;
  run_count: number;
  usage_input_tokens: number;
  usage_output_tokens: number;
  usage_total_tokens: number;
  last_run_at: string | null;
}

export interface AdminEnterpriseList {
  items: AdminEnterpriseRow[];
  total: number;
}

export interface AdminUserRow {
  id: string;
  enterprise_id: string;
  enterprise_code: string;
  enterprise_name: string;
  username: string;
  display_name: string;
  role: "enterprise_admin" | "employee";
  status: string;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserPage {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export function adminLogin(username: string, password: string): Promise<AdminSession> {
  return requestJson<AdminSession>("/admin/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getAdminOverview(token: string): Promise<AdminOverview> {
  return requestJson<AdminOverview>("/admin/overview", { headers: authHeaders(token) });
}

export function listAdminEnterprises(token: string, q?: string): Promise<AdminEnterpriseList> {
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  return requestJson<AdminEnterpriseList>(`/admin/enterprises${query}`, {
    headers: authHeaders(token),
  });
}

export function listAdminUsers(
  token: string,
  params: { page?: number; pageSize?: number; q?: string; enterpriseId?: string } = {},
): Promise<AdminUserPage> {
  const query = new URLSearchParams();
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));
  if (params.q) query.set("q", params.q);
  if (params.enterpriseId) query.set("enterprise_id", params.enterpriseId);
  return requestJson<AdminUserPage>(`/admin/users?${query.toString()}`, {
    headers: authHeaders(token),
  });
}

export function updateAdminUserStatus(
  token: string,
  userId: string,
  status: "active" | "disabled",
): Promise<AdminUserRow> {
  return requestJson<AdminUserRow>(`/admin/users/${encodeURIComponent(userId)}/status`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify({ status }),
  });
}

export function resetAdminUserPassword(
  token: string,
  userId: string,
  password: string,
): Promise<{ deleted: boolean }> {
  return requestJson<{ deleted: boolean }>(
    `/admin/users/${encodeURIComponent(userId)}/reset-password`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ password }),
    },
  );
}
