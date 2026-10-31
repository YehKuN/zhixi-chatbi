import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/workspace" },
    { path: "/workspace", component: () => import("@/views/ChatBIDashboard.vue") },
    { path: "/analysis", component: () => import("@/views/WorkspaceView.vue") },
    { path: "/datasources", component: () => import("@/views/DatasourcesView.vue") },
    { path: "/settings/model", component: () => import("@/views/ModelSettingsView.vue") },
  ],
});
