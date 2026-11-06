export interface StoredAdminSession {
  token: string;
  expiresAt: string | null;
}

const STORAGE_KEY = "chatbi.admin.v1";

function getStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** 管理台令牌只放 sessionStorage，关闭标签页即失效，不与企业登录共享。 */
export function readAdminSession(): StoredAdminSession | null {
  const raw = getStorage()?.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as StoredAdminSession).token === "string"
    ) {
      return parsed as StoredAdminSession;
    }
    return null;
  } catch {
    return null;
  }
}

export function writeAdminSession(session: StoredAdminSession): void {
  getStorage()?.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearAdminSession(): void {
  getStorage()?.removeItem(STORAGE_KEY);
}
