import { requestJson } from "./client";

export type AuthRole = "enterprise_admin" | "employee";

export interface AuthEnterprise {
  code: string;
  name: string;
  industry: string | null;
  company_size: string | null;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  role: AuthRole;
  created_at: string;
}

export interface AuthSession {
  token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
  enterprise: AuthEnterprise;
}

export interface AuthProfile {
  user: AuthUser;
  enterprise: AuthEnterprise;
}

export interface EnterpriseRegisterPayload {
  company_name: string;
  industry: string | null;
  company_size: string | null;
  contact_name: string;
  contact_phone: string;
  contact_email: string | null;
  username: string;
  display_name: string;
  password: string;
}

export interface EmployeeRegisterPayload {
  enterprise_code: string;
  username: string;
  display_name: string;
  password: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LogoutResult {
  logged_out: boolean;
}

export function registerEnterprise(
  payload: EnterpriseRegisterPayload,
): Promise<AuthSession> {
  return requestJson<AuthSession>("/auth/enterprises/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function registerEmployee(
  payload: EmployeeRegisterPayload,
): Promise<AuthSession> {
  return requestJson<AuthSession>("/auth/employees/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: LoginPayload): Promise<AuthSession> {
  return requestJson<AuthSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMe(): Promise<AuthProfile> {
  return requestJson<AuthProfile>("/auth/me");
}

export function logout(token: string): Promise<LogoutResult> {
  return requestJson<LogoutResult>("/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}
