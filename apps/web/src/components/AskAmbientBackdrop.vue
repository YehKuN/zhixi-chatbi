<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

import { useTheme } from "@/lib/theme";

interface AmbientConfig {
  enabled: boolean;
  halo: boolean;
  density: number;
}

interface FloatingItem {
  id: number;
  text?: string;
  style: Record<string, string>;
}

interface Ripple {
  id: number;
  x: number;
  y: number;
}

interface FlowParticle {
  x: number;
  y: number;
  radius: number;
  glow: number;
  speed: number;
  swayAmp: number;
  swayFreq: number;
  phase: number;
  tonal: number;
  offsetX: number;
  offsetY: number;
  hover: number;
}

declare global {
  interface Window {
    /** 全局开关：window.__CHATBI_AMBIENT__ = { enabled: false } / { halo: false } / { density: 1.4 } */
    __CHATBI_AMBIENT__?: Partial<AmbientConfig>;
  }
}

const DENSITY_MIN = 0.4;
const DENSITY_MAX = 2;

function readConfig(): AmbientConfig {
  const raw = typeof window === "undefined" ? undefined : window.__CHATBI_AMBIENT__;
  const density = typeof raw?.density === "number" && Number.isFinite(raw.density)
    ? Math.min(DENSITY_MAX, Math.max(DENSITY_MIN, raw.density))
    : 1;
  return {
    enabled: raw?.enabled !== false,
    halo: raw?.halo !== false,
    density,
  };
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

const config = readConfig();
const { isDark } = useTheme();
const motion = !prefersReducedMotion();
const compact = typeof window !== "undefined" && window.innerWidth < 720;
const density = config.density * (compact ? 0.55 : 1);

function buildGrids(count: number): FloatingItem[] {
  return Array.from({ length: Math.round(count) }, (_, index) => ({
    id: index,
    style: {
      "--x": `${randomBetween(4, 94).toFixed(2)}%`,
      "--y": `${randomBetween(6, 92).toFixed(2)}%`,
      "--w": `${randomBetween(38, 92).toFixed(0)}px`,
      "--h": `${randomBetween(28, 64).toFixed(0)}px`,
      "--o": randomBetween(0.16, 0.3).toFixed(2),
      "--dur": `${randomBetween(26, 44).toFixed(1)}s`,
      "--delay": `-${randomBetween(0, 30).toFixed(1)}s`,
      "--dx": `${randomBetween(-30, 30).toFixed(0)}px`,
      "--dy": `${randomBetween(-24, 24).toFixed(0)}px`,
    },
  }));
}

const grids = motion ? buildGrids(6 * density) : [];
const digitTexts = ["04 17 29 88", "Q3 · 12.4%", "1,024 rows", "σ 0.82", "2025 / 11", "7.6%"];
const digits = motion
  ? digitTexts.map((text, index) => ({
    id: index,
    text,
    style: {
      "--x": `${randomBetween(6, 88).toFixed(2)}%`,
      "--y": `${randomBetween(10, 88).toFixed(2)}%`,
      "--o": randomBetween(0.05, 0.09).toFixed(3),
      "--dur": `${randomBetween(28, 46).toFixed(1)}s`,
      "--delay": `-${randomBetween(0, 32).toFixed(1)}s`,
      "--dx": `${randomBetween(-18, 18).toFixed(0)}px`,
      "--dy": `${randomBetween(-16, 16).toFixed(0)}px`,
    },
  }))
  : [];
const axes = motion
  ? [0, 1, 2].map((index) => ({
    id: index,
    style: {
      "--x": `${randomBetween(8, 86).toFixed(2)}%`,
      "--y": `${randomBetween(14, 86).toFixed(2)}%`,
      "--w": `${randomBetween(90, 180).toFixed(0)}px`,
      "--o": randomBetween(0.14, 0.24).toFixed(2),
      "--dur": `${randomBetween(30, 48).toFixed(1)}s`,
      "--delay": `-${randomBetween(0, 30).toFixed(1)}s`,
      "--dx": `${randomBetween(-16, 16).toFixed(0)}px`,
      "--dy": `${randomBetween(-12, 12).toFixed(0)}px`,
    },
  }))
  : [];

const root = ref<HTMLElement | null>(null);
const canvasEl = ref<HTMLCanvasElement | null>(null);
const pointerActive = ref(false);
const ripples = ref<Ripple[]>([]);
const rippleTimers = new Set<ReturnType<typeof setTimeout>>();
const flowParticles: FlowParticle[] = [];

let host: HTMLElement | null = null;
let frame = 0;
let flowFrame = 0;
let flowLast = 0;
let flowWidth = 0;
let flowHeight = 0;
let flowObserver: ResizeObserver | null = null;
let lightSprites: HTMLCanvasElement[] = [];
let darkSprites: HTMLCanvasElement[] = [];

const PARTICLE_RAMP_LIGHT = ["70, 86, 152", "88, 104, 172", "110, 126, 192", "134, 150, 208", "160, 174, 222"];
const PARTICLE_RAMP_DARK = ["136, 156, 240", "156, 174, 250", "176, 192, 255", "196, 208, 255", "218, 228, 255"];
let haloX = 0;
let haloY = 0;
let targetX = 0;
let targetY = 0;
let shiftX = 0;
let shiftY = 0;
let shiftTargetX = 0;
let shiftTargetY = 0;
let rippleId = 0;

function ensureFrame(): void {
  if (frame === 0) frame = requestAnimationFrame(tick);
}

function tick(): void {
  frame = 0;
  const element = root.value;
  if (element === null) return;
  haloX += (targetX - haloX) * 0.16;
  haloY += (targetY - haloY) * 0.16;
  shiftX += (shiftTargetX - shiftX) * 0.07;
  shiftY += (shiftTargetY - shiftY) * 0.07;
  const halo = element.querySelector<HTMLElement>(".ambient-halo");
  if (halo !== null) {
    halo.style.transform = `translate3d(${haloX.toFixed(1)}px, ${haloY.toFixed(1)}px, 0)`;
  }
  element.style.setProperty("--px", shiftX.toFixed(4));
  element.style.setProperty("--py", shiftY.toFixed(4));
  const settling = Math.abs(targetX - haloX) > 0.3
    || Math.abs(targetY - haloY) > 0.3
    || Math.abs(shiftTargetX - shiftX) > 0.002
    || Math.abs(shiftTargetY - shiftY) > 0.002;
  if (settling) ensureFrame();
}

function onPointerMove(event: PointerEvent): void {
  const element = root.value;
  if (element === null) return;
  const rect = element.getBoundingClientRect();
  targetX = event.clientX - rect.left;
  targetY = event.clientY - rect.top;
  shiftTargetX = (targetX / Math.max(rect.width, 1)) * 2 - 1;
  shiftTargetY = (targetY / Math.max(rect.height, 1)) * 2 - 1;
  if (!pointerActive.value) {
    pointerActive.value = true;
    haloX = targetX;
    haloY = targetY;
    const halo = element.querySelector<HTMLElement>(".ambient-halo");
    if (halo !== null) halo.style.transform = `translate3d(${targetX.toFixed(1)}px, ${targetY.toFixed(1)}px, 0)`;
  }
  ensureFrame();
}

function onPointerLeave(): void {
  pointerActive.value = false;
  shiftTargetX = 0;
  shiftTargetY = 0;
  ensureFrame();
}

function onPointerDown(event: PointerEvent): void {
  const element = root.value;
  if (element === null || !config.halo) return;
  const rect = element.getBoundingClientRect();
  const id = (rippleId += 1);
  ripples.value = [...ripples.value, { id, x: event.clientX - rect.left, y: event.clientY - rect.top }];
  const timer = setTimeout(() => {
    ripples.value = ripples.value.filter((item) => item.id !== id);
    rippleTimers.delete(timer);
  }, 760);
  rippleTimers.add(timer);
}

function createBubbleSprite(rgb: string): HTMLCanvasElement {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context !== null) {
    const center = size / 2;
    // 泡沫膜：中心近乎透明，只在边缘留一圈薄光，看起来像水里的气泡而不是实心光点。
    const film = context.createRadialGradient(center, center, 0, center, center, center);
    film.addColorStop(0, `rgba(${rgb}, 0.02)`);
    film.addColorStop(0.62, `rgba(${rgb}, 0.05)`);
    film.addColorStop(0.83, `rgba(${rgb}, 0.6)`);
    film.addColorStop(1, `rgba(${rgb}, 0)`);
    context.fillStyle = film;
    context.beginPath();
    context.arc(center, center, center, 0, Math.PI * 2);
    context.fill();
    // 下缘稍厚的折射边，让圆环比均匀光圈更立体。
    const shade = context.createRadialGradient(
      center + size * 0.02,
      center + size * 0.05,
      0,
      center + size * 0.02,
      center + size * 0.05,
      center,
    );
    shade.addColorStop(0, `rgba(${rgb}, 0)`);
    shade.addColorStop(0.72, `rgba(${rgb}, 0)`);
    shade.addColorStop(0.9, `rgba(${rgb}, 0.26)`);
    shade.addColorStop(1, `rgba(${rgb}, 0)`);
    context.fillStyle = shade;
    context.beginPath();
    context.arc(center, center, center, 0, Math.PI * 2);
    context.fill();
  }
  return canvas;
}

function seedFlowParticles(): void {
  flowParticles.length = 0;
  const count = Math.round(240 * density);
  for (let index = 0; index < count; index += 1) {
    const near = Math.random() < 0.28;
    flowParticles.push({
      x: Math.random() * Math.max(flowWidth, 1),
      y: Math.random() * Math.max(flowHeight, 1),
      radius: near ? randomBetween(2.4, 4) : randomBetween(1.3, 2.4),
      glow: near ? randomBetween(1.3, 1.55) : randomBetween(1.2, 1.4),
      speed: near ? randomBetween(5, 10) : randomBetween(8, 16),
      swayAmp: randomBetween(6, 22),
      swayFreq: randomBetween(0.16, 0.5),
      phase: Math.random() * Math.PI * 2,
      tonal: randomBetween(0.8, 1.2),
      offsetX: 0,
      offsetY: 0,
      hover: 0,
    });
  }
}

function resizeFlow(): void {
  const canvas = canvasEl.value;
  const element = root.value;
  if (canvas === null || element === null) return;
  const rect = element.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const previousWidth = flowWidth;
  const previousHeight = flowHeight;
  flowWidth = Math.max(rect.width, 1);
  flowHeight = Math.max(rect.height, 1);
  canvas.width = Math.round(flowWidth * dpr);
  canvas.height = Math.round(flowHeight * dpr);
  canvas.getContext("2d")?.setTransform(dpr, 0, 0, dpr, 0, 0);
  for (const particle of flowParticles) {
    particle.x = previousWidth > 0 ? (particle.x / previousWidth) * flowWidth : Math.random() * flowWidth;
    particle.y = previousHeight > 0 ? (particle.y / previousHeight) * flowHeight : Math.random() * flowHeight;
  }
}

const ATTRACT_RADIUS = 190;

function flowStep(now: number): void {
  flowFrame = requestAnimationFrame(flowStep);
  const canvas = canvasEl.value;
  if (canvas === null) return;
  const context = canvas.getContext("2d");
  if (context === null || flowWidth === 0) return;
  const delta = flowLast === 0 ? 0.016 : Math.min((now - flowLast) / 1000, 0.05);
  flowLast = now;
  context.clearRect(0, 0, flowWidth, flowHeight);

  const sprites = isDark.value ? darkSprites : lightSprites;
  if (sprites.length === 0) return;
  const attract = config.halo && pointerActive.value;
  const seconds = now / 1000;
  const ease = 1 - Math.exp(-delta * 5.5);

  for (const particle of flowParticles) {
    particle.y -= particle.speed * delta;
    if (particle.y < -20) {
      particle.y = flowHeight + randomBetween(4, 24);
      particle.x = Math.random() * flowWidth;
      particle.offsetX = 0;
      particle.offsetY = 0;
      particle.hover = 0;
    }

    const sway = Math.sin(seconds * particle.swayFreq + particle.phase) * particle.swayAmp;
    let targetOffsetX = 0;
    let targetOffsetY = 0;
    let targetHover = 0;
    if (attract) {
      const dx = haloX - (particle.x + sway);
      const dy = haloY - particle.y;
      const distance = Math.hypot(dx, dy);
      if (distance < ATTRACT_RADIUS) {
        const falloff = 1 - distance / ATTRACT_RADIUS;
        // falloff^1.5：外围轻微偏转，靠近光晕的泡沫聚得更紧。
        const pull = falloff * Math.sqrt(falloff) * 0.9;
        targetOffsetX = dx * pull;
        targetOffsetY = dy * pull;
        targetHover = falloff;
      }
    }
    // 平滑吸附与回位：鼠标移开时粒子慢慢回到自己的上浮轨迹，不会突然消失。
    particle.offsetX += (targetOffsetX - particle.offsetX) * ease;
    particle.offsetY += (targetOffsetY - particle.offsetY) * ease;
    particle.hover += (targetHover - particle.hover) * ease;

    // 由深到浅：底部水色更实，越往上泡沫越淡。
    const lightness = Math.min(1, Math.max(0, 1 - particle.y / flowHeight));
    const level = Math.min(
      sprites.length - 1,
      Math.max(0, Math.round((lightness * 0.8 + particle.hover * 0.55) * (sprites.length - 1))),
    );
    const alpha = Math.min(0.72, (0.16 + 0.3 * (1 - lightness)) * (1 + particle.hover * 1.4) * particle.tonal);
    const x = particle.x + sway + particle.offsetX;
    const y = particle.y + particle.offsetY;
    // 轻微呼吸缩放，让泡沫有薄厚变化。
    const breathe = 1 + Math.sin(seconds * 0.7 + particle.phase) * 0.07 + particle.hover * 0.35;
    const size = particle.radius * particle.glow * breathe;
    context.globalAlpha = alpha;
    context.drawImage(sprites[level], x - size, y - size, size * 2, size * 2);
  }
  context.globalAlpha = 1;
}

function startFlow(): void {
  const canvas = canvasEl.value;
  const element = root.value;
  if (canvas === null || element === null) return;
  lightSprites = PARTICLE_RAMP_LIGHT.map((rgb) => createBubbleSprite(rgb));
  darkSprites = PARTICLE_RAMP_DARK.map((rgb) => createBubbleSprite(rgb));
  resizeFlow();
  seedFlowParticles();
  flowObserver = new ResizeObserver(() => resizeFlow());
  flowObserver.observe(element);
  flowFrame = requestAnimationFrame(flowStep);
}

onMounted(() => {
  const element = root.value;
  if (element === null) return;
  requestAnimationFrame(() => element.classList.add("is-entered"));
  if (!motion) return;
  host = element.parentElement;
  host?.addEventListener("pointermove", onPointerMove, { passive: true });
  host?.addEventListener("pointerleave", onPointerLeave, { passive: true });
  host?.addEventListener("pointerdown", onPointerDown, { passive: true });
  startFlow();
});

onBeforeUnmount(() => {
  host?.removeEventListener("pointermove", onPointerMove);
  host?.removeEventListener("pointerleave", onPointerLeave);
  host?.removeEventListener("pointerdown", onPointerDown);
  host = null;
  if (frame !== 0) cancelAnimationFrame(frame);
  frame = 0;
  if (flowFrame !== 0) cancelAnimationFrame(flowFrame);
  flowFrame = 0;
  flowObserver?.disconnect();
  flowObserver = null;
  flowParticles.length = 0;
  for (const timer of rippleTimers) clearTimeout(timer);
  rippleTimers.clear();
});
</script>

<template>
  <div
    v-if="config.enabled"
    ref="root"
    class="ambient"
    :class="{ 'is-pointer': pointerActive, 'is-dark': isDark }"
    aria-hidden="true"
  >
    <div class="ambient-gradient" />

    <div v-if="motion" class="ambient-sea">
      <i class="sea-shaft shaft-a" />
      <i class="sea-shaft shaft-b" />
      <i class="sea-floor" />
    </div>

    <div v-if="motion" class="ambient-flow">
      <i class="ambient-glow glow-a" />
      <i class="ambient-glow glow-b" />
      <i class="ambient-glow glow-c" />
    </div>

    <canvas v-if="motion" ref="canvasEl" class="ambient-particles" />

    <div v-if="motion" class="ambient-depth far">
      <span
        v-for="grid in grids"
        :key="`g-${grid.id}`"
        class="ambient-grid"
        :style="grid.style"
      />
      <span
        v-for="digit in digits"
        :key="`d-${digit.id}`"
        class="ambient-digit"
        :style="digit.style"
      >{{ digit.text }}</span>
      <span
        v-for="axis in axes"
        :key="`a-${axis.id}`"
        class="ambient-axis"
        :style="axis.style"
      />
    </div>

    <span v-if="motion && config.halo" class="ambient-halo" />

    <div v-if="motion && config.halo" class="ambient-ripples">
      <span
        v-for="ripple in ripples"
        :key="ripple.id"
        class="ambient-ripple"
        :style="{ left: `${ripple.x}px`, top: `${ripple.y}px` }"
      />
    </div>
  </div>
</template>

<style scoped>
.ambient {
  position: absolute;
  z-index: 0;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  contain: layout paint style;
  --px: 0;
  --py: 0;
}

.ambient-gradient {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(115% 85% at 50% -12%, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0) 62%),
    radial-gradient(70% 60% at 90% 6%, rgba(214, 223, 255, 0.5), transparent 64%),
    radial-gradient(72% 62% at 6% 94%, rgba(216, 235, 247, 0.46), transparent 62%),
    linear-gradient(180deg, #f8fafd 0%, #f3f6fb 52%, #edf2f9 100%);
  opacity: 0;
  transition: opacity 1.1s ease;
}
.ambient.is-entered .ambient-gradient { opacity: 1; }

/* 海底氛围：斜射的弱光柱 + 底部水色沉积，只做极淡的层次，不抢正文。 */
.ambient-sea {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 1.6s ease 0.3s;
}
.ambient.is-entered .ambient-sea { opacity: 1; }

.sea-shaft {
  position: absolute;
  top: -22%;
  display: block;
  height: 132%;
  filter: blur(16px);
  background: linear-gradient(180deg, rgba(186, 220, 240, 0.3), rgba(186, 220, 240, 0) 76%);
  will-change: transform, opacity;
}
.shaft-a {
  left: 14%;
  width: 150px;
  transform: rotate(11deg);
  animation: sea-shaft-a 24s ease-in-out infinite alternate;
}
.shaft-b {
  right: 16%;
  width: 210px;
  background: linear-gradient(180deg, rgba(198, 214, 250, 0.24), rgba(198, 214, 250, 0) 72%);
  transform: rotate(-9deg);
  animation: sea-shaft-b 32s ease-in-out infinite alternate;
}
.sea-floor {
  position: absolute;
  inset: auto 0 0 0;
  height: 44%;
  background: radial-gradient(115% 80% at 50% 110%, rgba(158, 202, 226, 0.36), rgba(158, 202, 226, 0) 72%);
}

.ambient-flow {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 1.8s ease 0.15s;
}
.ambient.is-entered .ambient-flow { opacity: 1; }

.ambient-glow {
  position: absolute;
  display: block;
  border-radius: 50%;
  opacity: 0.55;
  will-change: transform;
}
.glow-a {
  top: -12%;
  left: -8%;
  width: 520px;
  height: 420px;
  background: radial-gradient(circle, rgba(176, 196, 255, 0.5), transparent 66%);
  animation: ambient-flow-a 32s ease-in-out infinite alternate;
}
.glow-b {
  top: 16%;
  right: -10%;
  width: 460px;
  height: 380px;
  background: radial-gradient(circle, rgba(214, 203, 255, 0.42), transparent 66%);
  animation: ambient-flow-b 38s ease-in-out infinite alternate;
}
.glow-c {
  bottom: -18%;
  left: 26%;
  width: 560px;
  height: 420px;
  background: radial-gradient(circle, rgba(188, 226, 246, 0.44), transparent 68%);
  animation: ambient-flow-c 42s ease-in-out infinite alternate;
}

.ambient-depth {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 1.9s ease 0.25s;
  will-change: transform;
}
.ambient.is-entered .ambient-depth { opacity: 1; }
.ambient-depth.far {
  transform: translate3d(calc(var(--px) * 9px), calc(var(--py) * 9px), 0);
}

.ambient-particles {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  transform: translate3d(calc(var(--px) * 9px), calc(var(--py) * 9px), 0);
  transition: opacity 1.9s ease 0.25s;
  will-change: transform;
}
.ambient.is-entered .ambient-particles { opacity: 1; }

.ambient-grid {
  position: absolute;
  top: var(--y);
  left: var(--x);
  width: var(--w);
  height: var(--h);
  background-image: radial-gradient(circle, rgba(108, 122, 178, 0.55) 1px, transparent 1.3px);
  background-size: 8px 8px;
  opacity: var(--o);
  animation: ambient-drift var(--dur) ease-in-out var(--delay) infinite alternate;
  will-change: transform;
}

.ambient-digit {
  position: absolute;
  top: var(--y);
  left: var(--x);
  color: rgba(84, 100, 158, 0.85);
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  opacity: var(--o);
  animation: ambient-drift var(--dur) ease-in-out var(--delay) infinite alternate;
  will-change: transform;
}

.ambient-axis {
  position: absolute;
  top: var(--y);
  left: var(--x);
  width: var(--w);
  height: 7px;
  border-bottom: 1px solid rgba(120, 132, 185, 0.4);
  background-image: repeating-linear-gradient(90deg, rgba(120, 132, 185, 0.42) 0 1px, transparent 1px 8px);
  opacity: var(--o);
  animation: ambient-drift var(--dur) ease-in-out var(--delay) infinite alternate;
  will-change: transform;
}

.ambient-halo {
  position: absolute;
  top: 0;
  left: 0;
  width: 168px;
  height: 168px;
  margin: -84px 0 0 -84px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(126, 142, 255, 0.38) 0%, rgba(126, 142, 255, 0.14) 42%, transparent 70%);
  opacity: 0;
  transition: opacity 0.5s ease;
  will-change: transform;
}
.ambient.is-pointer .ambient-halo { opacity: 1; }

.ambient-ripples { position: absolute; inset: 0; }
.ambient-ripple {
  position: absolute;
  width: 180px;
  height: 180px;
  margin: -90px 0 0 -90px;
  border-radius: 50%;
  border: 1px solid rgba(126, 142, 255, 0.32);
  background: radial-gradient(circle, rgba(126, 142, 255, 0.16) 0%, transparent 62%);
  transform: translate3d(0, 0, 0) scale(0.35);
  opacity: 0.55;
  animation: ambient-ripple 0.72s cubic-bezier(0.22, 0.61, 0.36, 1) forwards;
}

/* 深色主题：深灰蓝渐变 + 冷白蓝光点，透明度同样压低，保证正文与输入清晰。 */
.ambient.is-dark .ambient-gradient {
  background:
    radial-gradient(115% 85% at 50% -12%, rgba(42, 54, 76, 0.85), rgba(42, 54, 76, 0) 62%),
    radial-gradient(70% 60% at 90% 6%, rgba(64, 72, 132, 0.42), transparent 64%),
    radial-gradient(72% 62% at 6% 94%, rgba(38, 84, 106, 0.34), transparent 62%),
    linear-gradient(180deg, #0b0f16 0%, #0c1119 52%, #090d13 100%);
}
.ambient.is-dark .sea-shaft {
  background: linear-gradient(180deg, rgba(96, 186, 216, 0.16), rgba(96, 186, 216, 0) 76%);
}
.ambient.is-dark .shaft-b {
  background: linear-gradient(180deg, rgba(110, 168, 230, 0.13), rgba(110, 168, 230, 0) 72%);
}
.ambient.is-dark .sea-floor {
  background: radial-gradient(115% 80% at 50% 110%, rgba(38, 116, 138, 0.34), rgba(38, 116, 138, 0) 72%);
}
.ambient.is-dark .glow-a { background: radial-gradient(circle, rgba(72, 96, 170, 0.34), transparent 66%); }
.ambient.is-dark .glow-b { background: radial-gradient(circle, rgba(116, 96, 176, 0.3), transparent 66%); }
.ambient.is-dark .glow-c { background: radial-gradient(circle, rgba(64, 132, 160, 0.3), transparent 68%); }
.ambient.is-dark .ambient-grid {
  background-image: radial-gradient(circle, rgba(150, 168, 226, 0.5) 1px, transparent 1.3px);
}
.ambient.is-dark .ambient-digit { color: rgba(178, 192, 232, 0.85); }
.ambient.is-dark .ambient-axis {
  border-bottom-color: rgba(140, 156, 208, 0.38);
  background-image: repeating-linear-gradient(90deg, rgba(140, 156, 208, 0.4) 0 1px, transparent 1px 8px);
}
.ambient.is-dark .ambient-halo {
  background: radial-gradient(circle, rgba(168, 186, 255, 0.3) 0%, rgba(150, 168, 255, 0.12) 42%, transparent 70%);
}
.ambient.is-dark .ambient-ripple {
  border-color: rgba(168, 186, 255, 0.34);
  background: radial-gradient(circle, rgba(168, 186, 255, 0.14) 0%, transparent 62%);
}

@keyframes sea-shaft-a {
  from { transform: rotate(11deg) translate3d(-10px, 0, 0); opacity: 0.55; }
  to { transform: rotate(11deg) translate3d(18px, 26px, 0); opacity: 0.9; }
}
@keyframes sea-shaft-b {
  from { transform: rotate(-9deg) translate3d(12px, 10px, 0); opacity: 0.9; }
  to { transform: rotate(-9deg) translate3d(-16px, -18px, 0); opacity: 0.5; }
}

@keyframes ambient-drift {
  from { transform: translate3d(0, 0, 0); }
  to { transform: translate3d(var(--dx), var(--dy), 0); }
}

@keyframes ambient-flow-a {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(34px, 26px, 0) scale(1.08); }
}
@keyframes ambient-flow-b {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(-28px, 32px, 0) scale(1.06); }
}
@keyframes ambient-flow-c {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(24px, -30px, 0) scale(1.1); }
}

@keyframes ambient-ripple {
  from { opacity: 0.5; transform: translate3d(0, 0, 0) scale(0.35); }
  to { opacity: 0; transform: translate3d(0, 0, 0) scale(1.9); }
}

@media (prefers-reduced-motion: reduce) {
  .ambient-sea, .ambient-flow, .ambient-depth, .ambient-particles, .ambient-halo, .ambient-ripples { display: none; }
}
</style>
