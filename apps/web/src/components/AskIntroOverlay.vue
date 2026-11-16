<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";

import { isCompactViewport, type AskIntroConfig } from "@/lib/askIntro";
import { useTheme } from "@/lib/theme";

type ParticleKind = "digit" | "tick" | "dot" | "grid" | "polyline";
type IntroPhase = "gather" | "brand" | "closing" | "skipping";

interface Particle {
  id: number;
  kind: ParticleKind;
  text: string;
  style: Record<string, string>;
}

const props = defineProps<{ config: AskIntroConfig }>();
const emit = defineEmits<{ done: []; reveal: [fast?: boolean] }>();

const phase = ref<IntroPhase>("gather");
const { isDark } = useTheme();
const timers: ReturnType<typeof setTimeout>[] = [];

const titleChars = computed(() => Array.from(props.config.brand));

const timingStyle = computed<Record<string, string>>(() => ({
  "--fly": `${Math.round(props.config.duration * 0.25)}ms`,
  "--char-step": `${Math.round(props.config.duration * 0.014)}ms`,
  "--slogan-delay": `${Math.round(props.config.duration * 0.11)}ms`,
  "--halo": `${Math.round(props.config.duration * 0.44)}ms`,
  "--ripple": `${Math.round(props.config.duration * 0.5)}ms`,
}));

function pickKind(): ParticleKind {
  const roll = Math.random();
  if (roll < 0.4) return "digit";
  if (roll < 0.62) return "tick";
  if (roll < 0.82) return "dot";
  if (roll < 0.92) return "grid";
  return "polyline";
}

function buildParticles(): Particle[] {
  const count = isCompactViewport() ? 90 : 220;
  const width = typeof window === "undefined" ? 1440 : window.innerWidth;
  const height = typeof window === "undefined" ? 900 : window.innerHeight;
  const radius = Math.max(width, height) * 0.62;
  return Array.from({ length: count }, (_, index) => {
    const kind = pickKind();
    const angle = Math.random() * Math.PI * 2;
    const distance = radius * (0.85 + Math.random() * 0.55);
    const spin = kind === "tick" || kind === "polyline" || kind === "grid";
    return {
      id: index,
      kind,
      text: kind === "digit" ? String(Math.floor(Math.random() * 10)) : "",
      style: {
        "--sx": `${Math.round(Math.cos(angle) * distance)}px`,
        "--sy": `${Math.round(Math.sin(angle) * distance)}px`,
        "--delay": `${Math.round(Math.random() * 140)}ms`,
        "--peak": (0.3 + Math.random() * 0.45).toFixed(2),
        "--scale": (0.7 + Math.random() * 0.5).toFixed(2),
        "--rot": `${spin ? Math.round(Math.random() * 360) : 0}deg`,
        "--digit-size": `${10 + Math.round(Math.random() * 3)}px`,
        "--tick-h": `${6 + Math.round(Math.random() * 7)}px`,
        "--dot-size": `${2 + Math.round(Math.random() * 2)}px`,
        "--grid-w": `${14 + Math.round(Math.random() * 12)}px`,
        "--grid-h": `${10 + Math.round(Math.random() * 10)}px`,
      },
    };
  });
}

const particles = buildParticles();

function later(task: () => void, delay: number): void {
  timers.push(setTimeout(task, delay));
}

function clearTimers(): void {
  while (timers.length > 0) {
    const timer = timers.pop();
    if (timer !== undefined) clearTimeout(timer);
  }
}

function skip(): void {
  if (phase.value === "closing" || phase.value === "skipping") return;
  clearTimers();
  phase.value = "skipping";
  emit("reveal", true);
  later(() => emit("done"), 300);
}

later(() => { phase.value = "brand"; }, props.config.duration * 0.25);
later(() => {
  phase.value = "closing";
  emit("reveal");
}, props.config.duration * 0.625);
later(() => emit("done"), props.config.duration);

onBeforeUnmount(clearTimers);
</script>

<template>
  <div class="ask-intro" :class="[`is-${phase}`, { 'is-dark': isDark }]" :style="timingStyle">
    <div class="intro-canvas" aria-hidden="true">
      <div class="intro-bg" />
      <div class="intro-noise" />
      <div class="intro-particles">
        <span
          v-for="particle in particles"
          :key="particle.id"
          class="intro-particle"
          :class="`kind-${particle.kind}`"
          :style="particle.style"
        >
          <span class="particle-body">
            <template v-if="particle.kind === 'digit'">{{ particle.text }}</template>
            <svg v-else-if="particle.kind === 'polyline'" viewBox="0 0 24 10" fill="none">
              <polyline points="0,8 6,3 12,7 18,2 24,6" stroke="rgba(96,118,205,0.85)" stroke-width="1.2" />
            </svg>
          </span>
        </span>
      </div>

      <div class="intro-stage">
        <span class="intro-halo" />
        <span class="intro-ripple r1" />
        <span class="intro-ripple r2" />
        <img class="intro-logo" src="/chatbi-mark.svg" alt="" />
        <h1 class="intro-title">
          <span v-for="(char, index) in titleChars" :key="index" :style="{ '--i': index }">{{ char }}</span>
        </h1>
        <p class="intro-slogan">{{ config.slogan }}</p>
      </div>
    </div>

    <button type="button" class="intro-skip" @click="skip">跳过动画</button>
  </div>
</template>

<style scoped>
.ask-intro {
  position: absolute;
  z-index: 40;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-family: "Manrope", "Noto Sans SC", Inter, system-ui, sans-serif;
}

.intro-canvas {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.intro-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(120% 90% at 18% 10%, rgba(213, 224, 255, 0.92), transparent 58%),
    radial-gradient(110% 90% at 84% 16%, rgba(233, 221, 255, 0.8), transparent 60%),
    radial-gradient(130% 100% at 50% 104%, rgba(212, 235, 255, 0.85), transparent 64%),
    linear-gradient(180deg, #f8fafd 0%, #eef3fa 55%, #e8eef7 100%);
  opacity: 1;
  transition: opacity 1.1s ease;
}
.is-closing .intro-bg, .is-skipping .intro-bg { opacity: 0; }

.intro-noise {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='160' height='160' filter='url(%23n)' opacity='0.5'/></svg>");
  opacity: 0.045;
  mix-blend-mode: multiply;
  transition: opacity 1.1s ease;
}
.is-closing .intro-noise, .is-skipping .intro-noise { opacity: 0; }
.is-skipping .intro-noise { transition-duration: 0.3s; }

.intro-particles { position: absolute; inset: 0; }

.intro-particle {
  position: absolute;
  top: 50%;
  left: 50%;
  opacity: 0;
  will-change: transform, opacity;
  animation: intro-converge var(--fly) cubic-bezier(0.215, 0.61, 0.355, 1) var(--delay) both;
}
.particle-body {
  display: block;
  transform: translate(-50%, -50%) rotate(var(--rot));
}

.kind-digit .particle-body {
  color: rgba(76, 96, 166, 0.72);
  font-size: var(--digit-size);
  font-weight: 500;
  text-shadow: 0 0 10px rgba(104, 128, 235, 0.55);
}
.kind-tick .particle-body {
  width: 1px;
  height: var(--tick-h);
  background: linear-gradient(180deg, rgba(110, 130, 220, 0.05), rgba(110, 130, 220, 0.9));
  box-shadow: 0 0 6px rgba(110, 130, 220, 0.5);
}
.kind-dot .particle-body {
  width: var(--dot-size);
  height: var(--dot-size);
  border-radius: 50%;
  background: rgba(104, 126, 208, 0.85);
  box-shadow: 0 0 8px rgba(104, 126, 208, 0.6);
}
.kind-grid .particle-body {
  width: var(--grid-w);
  height: var(--grid-h);
  background-image: radial-gradient(circle, rgba(92, 114, 190, 0.55) 1px, transparent 1.2px);
  background-size: 6px 6px;
  opacity: 0.6;
}
.kind-polyline .particle-body svg { display: block; width: 24px; height: 10px; filter: drop-shadow(0 0 3px rgba(96, 118, 205, 0.45)); }

.intro-stage {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 0 24px;
  text-align: center;
  transition: opacity 0.9s ease, transform 1s cubic-bezier(0.22, 0.61, 0.36, 1);
}
.is-closing .intro-stage, .is-skipping .intro-stage { opacity: 0; transform: translateY(-20px); }

.intro-halo {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 520px;
  height: 520px;
  margin: -260px 0 0 -260px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(132, 152, 255, 0.55) 0%, rgba(142, 160, 255, 0.22) 38%, transparent 70%);
  opacity: 0;
  transform: scale(0.4);
  pointer-events: none;
}
.is-brand .intro-halo { animation: intro-halo var(--halo) cubic-bezier(0.16, 0.84, 0.44, 1) both; }
.is-closing .intro-halo { opacity: 0; transform: scale(1.6); transition: opacity 0.8s ease, transform 1s ease; }

.intro-ripple {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 320px;
  height: 320px;
  margin: -160px 0 0 -160px;
  border: 1px solid rgba(118, 138, 226, 0.32);
  border-radius: 50%;
  opacity: 0;
  pointer-events: none;
}
.is-brand .intro-ripple.r1 { animation: intro-ripple var(--ripple) ease-out both; }
.is-brand .intro-ripple.r2 { animation: intro-ripple var(--ripple) ease-out 0.18s both; }

.intro-logo {
  width: 64px;
  height: 64px;
  object-fit: contain;
  opacity: 0;
  transform: scale(0.8);
}
.is-brand .intro-logo { animation: intro-logo 0.7s cubic-bezier(0.2, 0.7, 0.3, 1) both; }

.intro-title {
  display: flex;
  margin: 0;
  color: #2b3444;
  font-size: 29px;
  font-weight: 650;
  letter-spacing: 0.06em;
}
.intro-title span {
  display: inline-block;
  white-space: pre;
  opacity: 0;
  transform: translateY(16px);
}
.is-brand .intro-title span {
  animation: intro-char 0.62s cubic-bezier(0.22, 0.7, 0.32, 1) both;
  animation-delay: calc(var(--i) * var(--char-step));
}

.intro-slogan {
  margin: 0;
  color: #6d788c;
  font-size: 13px;
  letter-spacing: 0.12em;
  opacity: 0;
  transform: translateY(8px);
}
.is-brand .intro-slogan { animation: intro-slogan 0.7s ease-out var(--slogan-delay) both; }

.intro-skip {
  position: absolute;
  right: 24px;
  bottom: 24px;
  z-index: 5;
  display: inline-flex;
  height: 28px;
  align-items: center;
  border: 1px solid rgba(28, 43, 68, 0.12);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
  padding: 0 12px;
  color: #3a4455;
  font-size: 13px;
  cursor: pointer;
  backdrop-filter: blur(14px);
  transition: background 0.18s ease, transform 0.18s ease, border-color 0.18s ease, opacity 0.25s ease;
}
.intro-skip:hover { background: rgba(255, 255, 255, 0.92); border-color: rgba(28, 43, 68, 0.18); transform: scale(1.03); }
.intro-skip:active { transform: scale(0.97); }
.intro-skip:focus-visible { outline: 2px solid rgba(91, 107, 239, 0.55); outline-offset: 2px; }
.is-closing .intro-skip, .is-skipping .intro-skip { opacity: 0; pointer-events: none; }
.ask-intro.is-closing, .ask-intro.is-skipping { pointer-events: none; }

/* 深色主题：跟随全局夜间模式，底色换为深蓝黑，碎片与文字提亮。 */
.ask-intro.is-dark .intro-bg {
  background:
    radial-gradient(120% 90% at 18% 10%, rgba(34, 46, 74, 0.95), transparent 58%),
    radial-gradient(110% 90% at 84% 16%, rgba(52, 40, 78, 0.85), transparent 60%),
    radial-gradient(130% 100% at 50% 104%, rgba(24, 52, 66, 0.9), transparent 64%),
    linear-gradient(180deg, #0b0f16 0%, #0c1119 55%, #080c12 100%);
}
.ask-intro.is-dark .intro-noise { mix-blend-mode: screen; }
.ask-intro.is-dark .kind-digit .particle-body {
  color: rgba(176, 192, 236, 0.78);
  text-shadow: 0 0 10px rgba(120, 144, 255, 0.6);
}
.ask-intro.is-dark .kind-tick .particle-body {
  background: linear-gradient(180deg, rgba(150, 170, 255, 0.05), rgba(164, 182, 255, 0.9));
  box-shadow: 0 0 6px rgba(140, 160, 255, 0.55);
}
.ask-intro.is-dark .kind-dot .particle-body {
  background: rgba(172, 190, 255, 0.9);
  box-shadow: 0 0 8px rgba(140, 162, 255, 0.65);
}
.ask-intro.is-dark .kind-grid .particle-body {
  background-image: radial-gradient(circle, rgba(152, 170, 230, 0.55) 1px, transparent 1.2px);
}
.ask-intro.is-dark .kind-polyline .particle-body svg { filter: drop-shadow(0 0 3px rgba(140, 162, 255, 0.55)); }
.ask-intro.is-dark .kind-polyline polyline { stroke: rgba(160, 178, 240, 0.9); }
.ask-intro.is-dark .intro-title { color: #eaf0fb; }
.ask-intro.is-dark .intro-slogan { color: #96a2b6; }
.ask-intro.is-dark .intro-halo {
  background: radial-gradient(circle, rgba(132, 152, 255, 0.42) 0%, rgba(120, 142, 255, 0.16) 38%, transparent 70%);
}
.ask-intro.is-dark .intro-ripple { border-color: rgba(150, 170, 255, 0.34); }
.ask-intro.is-dark .intro-skip {
  border-color: rgba(255, 255, 255, 0.14);
  background: rgba(22, 27, 36, 0.6);
  color: #cdd6e2;
}
.ask-intro.is-dark .intro-skip:hover {
  border-color: rgba(255, 255, 255, 0.24);
  background: rgba(38, 45, 58, 0.78);
}

.is-skipping .intro-bg,
.is-skipping .intro-stage { transition-duration: 0.3s; }
.is-skipping .intro-particle { animation: none; opacity: 0; }

@keyframes intro-converge {
  0% {
    transform: translate3d(var(--sx), var(--sy), 0) scale(var(--scale));
    opacity: 0;
  }
  12% { opacity: var(--peak); }
  72% { opacity: var(--peak); }
  100% {
    transform: translate3d(0, 0, 0) scale(0.35);
    opacity: 0;
  }
}

@keyframes intro-halo {
  0% { opacity: 0; transform: scale(0.35); }
  32% { opacity: 0.9; transform: scale(1.02); }
  100% { opacity: 0.25; transform: scale(1.32); }
}

@keyframes intro-ripple {
  0% { opacity: 0.55; transform: scale(0.36); }
  100% { opacity: 0; transform: scale(1.95); }
}

@keyframes intro-logo {
  from { opacity: 0; transform: scale(0.8); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes intro-char {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes intro-slogan {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 720px) {
  .intro-title { font-size: 23px; }
  .intro-logo { width: 52px; height: 52px; }
  .intro-halo { width: 360px; height: 360px; margin: -180px 0 0 -180px; }
}
</style>
