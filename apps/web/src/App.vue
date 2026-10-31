<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { Activity, BarChart3, Database, FileText, LayoutDashboard, Moon, Settings2, Sun } from "@lucide/vue";
import { getHealth, type HealthResponse } from "@/api/client";
import { useTheme } from "@/lib/theme";

const health = ref<HealthResponse | null>(null);
const { isDark, toggleTheme } = useTheme();
const healthLabel = computed(() => health.value?.status ?? "演示模式");

onMounted(async () => {
  try {
    health.value = await getHealth();
  } catch {
    health.value = null;
  }
});
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell-light': !isDark }">
    <header class="app-topbar">
      <RouterLink class="app-brand" to="/workspace" aria-label="智析 ChatBI 工作台">
        <img class="app-brand-mark chatbi-brand-logo" src="/chatbi-mark.svg" alt="" aria-hidden="true" />
        <span class="app-brand-copy"><strong>智析 ChatBI</strong><small>企业数据智能中枢</small></span>
      </RouterLink>
      <nav class="app-nav" aria-label="主导航">
        <RouterLink to="/workspace"><LayoutDashboard :size="15" />工作台</RouterLink>
        <RouterLink to="/datasources"><Database :size="15" />数据资产</RouterLink>
        <RouterLink to="/settings/model"><Settings2 :size="15" />模型设置</RouterLink>
      </nav>
      <div class="app-topbar-end">
        <div class="topbar-date">2026 / 10 / 29 · 周四</div>
        <div class="system-chip"><span class="status-dot" /><span>{{ health ? '系统在线' : '演示模式' }}</span><small>{{ healthLabel }}</small></div>
        <button class="icon-button" type="button" :aria-label="isDark ? '切换浅色主题' : '切换深色主题'" @click="toggleTheme"><Sun v-if="isDark" :size="16" /><Moon v-else :size="16" /></button>
        <div class="profile-chip"><span class="profile-avatar">Y</span><span>运营分析师</span></div>
      </div>
    </header>
    <main class="app-content"><RouterView /></main>
  </div>
</template>
