export interface AskIntroConfig {
  enabled: boolean;
  duration: number;
  brand: string;
  slogan: string;
}

declare global {
  interface Window {
    /** 全局开关：window.__CHATBI_INTRO__ = { enabled: false, duration: 3200, brand: "智析 ChatBI", slogan: "..." } */
    __CHATBI_INTRO__?: Partial<AskIntroConfig>;
  }
}

const DEFAULT_DURATION = 3200;
const MOBILE_DURATION = 2000;
const MOBILE_MAX_WIDTH = 720;

const DEFAULT_BRAND = "智析 ChatBI";
const DEFAULT_SLOGAN = "让数据，直接回答业务问题";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function isCompactViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia(`(max-width: ${MOBILE_MAX_WIDTH}px)`).matches;
}

export function readAskIntroConfig(): AskIntroConfig {
  const raw = typeof window === "undefined" ? undefined : window.__CHATBI_INTRO__;
  const configured = typeof raw?.duration === "number" && raw.duration >= 1200 ? raw.duration : DEFAULT_DURATION;
  return {
    enabled: raw?.enabled !== false,
    duration: isCompactViewport() ? MOBILE_DURATION : configured,
    brand: typeof raw?.brand === "string" && raw.brand.trim() ? raw.brand.trim() : DEFAULT_BRAND,
    slogan: typeof raw?.slogan === "string" && raw.slogan.trim() ? raw.slogan.trim() : DEFAULT_SLOGAN,
  };
}
