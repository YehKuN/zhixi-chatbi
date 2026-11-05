import type { AuthEnterprise, AuthUser } from "@/api/auth";

export interface StoredAuthSession {
  token: string;
  user: AuthUser;
  enterprise: AuthEnterprise;
  expiresAt: string | null;
}

const STORAGE_KEY = "chatbi.auth.v1";

function getStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function isStoredSession(value: unknown): value is StoredAuthSession {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.token === "string" &&
    typeof candidate.user === "object" &&
    candidate.user !== null &&
    typeof candidate.enterprise === "object" &&
    candidate.enterprise !== null
  );
}

export function readAuthSession(): StoredAuthSession | null {
  const raw = getStorage()?.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    return isStoredSession(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function readAuthToken(): string | null {
  const session = readAuthSession();
  return session?.token ?? null;
}

export function writeAuthSession(session: StoredAuthSession): void {
  getStorage()?.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearAuthSession(): void {
  getStorage()?.removeItem(STORAGE_KEY);
}
