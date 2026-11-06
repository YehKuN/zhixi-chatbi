import { createRouter, createWebHistory } from "vue-router";

import { readAuthToken } from "@/lib/authStorage";

const protectedMeta = { requiresAuth: true };

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: () => import("@/views/AuthView.vue"), meta: { public: true } },
    { path: "/admin", component: () => import("@/views/AdminConsole.vue"), meta: { public: true } },
    {
      path: "/",
      redirect: () => (readAuthToken() ? "/workspace" : "/login"),
    },
    {
      path: "/workspace",
      component: () => import("@/views/ChatBIDashboard.vue"),
      meta: protectedMeta,
    },
    {
      path: "/analysis",
      component: () => import("@/views/WorkspaceView.vue"),
      meta: protectedMeta,
    },
    {
      path: "/datasources",
      component: () => import("@/views/DatasourcesView.vue"),
      meta: protectedMeta,
    },
    {
      path: "/settings/model",
      component: () => import("@/views/ModelSettingsView.vue"),
      meta: protectedMeta,
    },
  ],
});

router.beforeEach((to) => {
  const token = readAuthToken();
  if (to.path === "/login") {
    return token ? { path: "/workspace" } : true;
  }
  if (to.matched.some((record) => record.meta.requiresAuth) && !token) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  return true;
});
