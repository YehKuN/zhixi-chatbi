import { computed, ref } from "vue";

export type ThemeName = "dark" | "light";

// v2：默认主题切换为日间，旧版深色偏好不再沿用，避免老用户仍停留在夜间。
export const THEME_STORAGE_KEY = "chatbi.theme.v2";

// 日间模式为默认主题；用户首次访问或存储不可用时都落在浅色体系。
const DEFAULT_THEME: ThemeName = "light";

const theme = ref<ThemeName>(DEFAULT_THEME);

function isThemeName(value: string | null | undefined): value is ThemeName {
  return value === "dark" || value === "light";
}

export function readStoredTheme(): ThemeName {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (isThemeName(stored)) return stored;
  } catch {
    return DEFAULT_THEME;
  }
  return DEFAULT_THEME;
}

export function applyTheme(next: ThemeName): void {
  theme.value = next;
  const root = document.documentElement;
  root.dataset.theme = next;
  root.style.colorScheme = next;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // Private mode or quota: keep the in-memory theme.
  }
}

export function useTheme() {
  const isDark = computed(() => theme.value === "dark");
  function toggleTheme(): void {
    applyTheme(theme.value === "dark" ? "light" : "dark");
  }
  return { theme, isDark, toggleTheme };
}
