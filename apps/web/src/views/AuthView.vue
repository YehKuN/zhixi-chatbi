<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AlertCircle,
  ArrowRight,
  BadgeCheck,
  Building2,
  Check,
  ChevronRight,
  Copy,
  Database,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Mail,
  Phone,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  UserRound,
  UsersRound,
} from "@lucide/vue";

import { ApiClientError } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";

type Tab = "login" | "enterprise" | "employee";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const activeTab = ref<Tab>("login");
const entered = ref(false);
const submitting = ref(false);
const errorMessage = ref("");
const showPassword = ref(false);
const issuedCode = ref<string | null>(null);
const issuedCompany = ref("");
const copied = ref(false);

const industryOptions = [
  "互联网 / 软件",
  "制造业",
  "零售 / 电商",
  "金融 / 保险",
  "物流 / 供应链",
  "教育",
  "医疗健康",
  "其他",
];
const sizeOptions = ["1-50 人", "51-200 人", "201-500 人", "501-1000 人", "1000 人以上"];

const loginForm = reactive({ username: "", password: "" });
const enterpriseForm = reactive({
  company_name: "",
  industry: "",
  company_size: "",
  contact_name: "",
  contact_phone: "",
  contact_email: "",
  username: "",
  display_name: "",
  password: "",
});
const employeeForm = reactive({
  enterprise_code: "",
  username: "",
  display_name: "",
  password: "",
});

const tabs: { id: Tab; label: string; icon: typeof UserRound }[] = [
  { id: "login", label: "账号登录", icon: UserRound },
  { id: "enterprise", label: "企业入驻", icon: Building2 },
  { id: "employee", label: "员工加入", icon: UsersRound },
];
const tabIndex = computed(() => tabs.findIndex((tab) => tab.id === activeTab.value));
const isSuccess = computed(() => activeTab.value === "enterprise" && issuedCode.value !== null);

const panelTitle = computed(() => {
  if (isSuccess.value) return "企业入驻成功";
  if (activeTab.value === "enterprise") return "申请企业账号";
  if (activeTab.value === "employee") return "加入所属企业";
  return "欢迎回来";
});
const panelSubtitle = computed(() => {
  if (isSuccess.value) return "企业 ID 已生成，请妥善保存并分享给同事";
  if (activeTab.value === "enterprise") return "填写企业全称等信息，系统将自动分配企业 ID";
  if (activeTab.value === "employee") return "输入企业管理员提供的企业 ID 即可注册";
  return "登录智析 ChatBI，继续你的数据分析工作";
});

onMounted(() => {
  requestAnimationFrame(() => {
    window.setTimeout(() => {
      entered.value = true;
    }, 40);
  });
});

function switchTab(tab: Tab): void {
  if (activeTab.value === tab) return;
  activeTab.value = tab;
  errorMessage.value = "";
  showPassword.value = false;
  if (tab !== "enterprise") {
    issuedCode.value = null;
  }
}

function normalizeCode(event: Event): void {
  const target = event.target as HTMLInputElement;
  employeeForm.enterprise_code = target.value.toUpperCase();
}

function describeError(caught: unknown): string {
  if (caught instanceof ApiClientError) {
    const messages: Record<string, string> = {
      INVALID_CREDENTIALS: "用户名或密码错误，请检查后重试",
      USERNAME_TAKEN: "该用户名已被占用，请换一个",
      ENTERPRISE_ALREADY_REGISTERED: "该公司全称已完成注册，请向管理员获取企业 ID",
      INVALID_ENTERPRISE_CODE: "企业 ID 不存在或已停用，请向企业管理员确认",
      AUTH_REQUIRED: "登录状态已失效，请重新登录",
    };
    return messages[caught.code] ?? caught.message;
  }
  if (caught instanceof Error) return caught.message;
  return "网络异常，请稍后重试";
}

function redirectTarget(): string {
  const redirect = route.query.redirect;
  return typeof redirect === "string" && redirect.startsWith("/") ? redirect : "/workspace";
}

async function submitLogin(): Promise<void> {
  if (submitting.value) return;
  errorMessage.value = "";
  submitting.value = true;
  try {
    await auth.login({
      username: loginForm.username.trim(),
      password: loginForm.password,
    });
    await router.push(redirectTarget());
  } catch (caught) {
    errorMessage.value = describeError(caught);
  } finally {
    submitting.value = false;
  }
}

async function submitEnterprise(): Promise<void> {
  if (submitting.value) return;
  errorMessage.value = "";
  submitting.value = true;
  try {
    const session = await auth.registerEnterprise({
      company_name: enterpriseForm.company_name.trim(),
      industry: enterpriseForm.industry.trim() || null,
      company_size: enterpriseForm.company_size.trim() || null,
      contact_name: enterpriseForm.contact_name.trim(),
      contact_phone: enterpriseForm.contact_phone.trim(),
      contact_email: enterpriseForm.contact_email.trim() || null,
      username: enterpriseForm.username.trim(),
      display_name: enterpriseForm.display_name.trim(),
      password: enterpriseForm.password,
    });
    issuedCode.value = session.enterprise.code;
    issuedCompany.value = session.enterprise.name;
    copied.value = false;
  } catch (caught) {
    errorMessage.value = describeError(caught);
  } finally {
    submitting.value = false;
  }
}

async function submitEmployee(): Promise<void> {
  if (submitting.value) return;
  errorMessage.value = "";
  submitting.value = true;
  try {
    await auth.registerEmployee({
      enterprise_code: employeeForm.enterprise_code.trim().toUpperCase(),
      username: employeeForm.username.trim(),
      display_name: employeeForm.display_name.trim(),
      password: employeeForm.password,
    });
    await router.push(redirectTarget());
  } catch (caught) {
    errorMessage.value = describeError(caught);
  } finally {
    submitting.value = false;
  }
}

async function copyCode(): Promise<void> {
  if (issuedCode.value === null) return;
  try {
    await navigator.clipboard.writeText(issuedCode.value);
    copied.value = true;
    window.setTimeout(() => {
      copied.value = false;
    }, 2200);
  } catch {
    errorMessage.value = "复制失败，请手动记录企业 ID";
  }
}
</script>

<template>
  <section class="auth-page" :class="{ 'is-entered': entered }">
    <div class="auth-aurora aurora-a" aria-hidden="true" />
    <div class="auth-aurora aurora-b" aria-hidden="true" />
    <div class="auth-grid" aria-hidden="true" />

    <div class="auth-stage">
      <div class="auth-hero">
        <div class="hero-badge reveal reveal-1">
          <span class="badge-mark"><Sparkles :size="14" /></span>
          <span>智析 ChatBI · AI 企业数据智能中枢</span>
        </div>

        <h1 class="hero-title reveal reveal-2">
          智启未来<span class="title-dot">·</span>AI 企业<span class="title-accent">数据分析平台</span>
        </h1>
        <p class="hero-subtitle reveal reveal-3">
          从自然语言到可验证的经营洞察，让每一次分析都有数据、有证据、有结论。
        </p>

        <div class="hero-points reveal reveal-4">
          <span><ShieldCheck :size="14" />受控 SQL 只读网关</span>
          <span><BadgeCheck :size="14" />全链路证据追溯</span>
          <span><UsersRound :size="14" />企业多角色协作</span>
        </div>

        <div class="auth-visual" aria-hidden="true">
          <div class="visual-wave">
            <svg viewBox="0 0 860 220" preserveAspectRatio="none">
              <path d="M0 150 C 150 60, 260 210, 430 130 S 700 40, 860 120" />
              <path d="M0 175 C 170 95, 320 230, 500 150 S 720 75, 860 155" />
              <path d="M0 200 C 190 130, 360 250, 560 175 S 750 110, 860 190" />
            </svg>
          </div>

          <div class="orbit orbit-a" />
          <div class="orbit orbit-b" />

          <div class="ai-stage">
            <div class="ai-platform">
              <span class="platform-ring ring-one" />
              <span class="platform-ring ring-two" />
              <span class="platform-base" />
            </div>
            <div class="ai-halo" />
            <div class="ai-core">
              <span class="ai-letter">AI</span>
              <span class="ai-scan" />
            </div>
            <span class="ai-node node-a" />
            <span class="ai-node node-b" />
            <span class="ai-node node-c" />

            <div class="float-card float-database">
              <span class="float-icon"><Database :size="15" /></span>
              <span><small>数据接入</small><strong>12.6 万行</strong></span>
            </div>
            <div class="float-card float-trend">
              <span class="float-icon violet"><TrendingUp :size="15" /></span>
              <span><small>营收趋势</small><strong>+18.4%</strong></span>
            </div>
            <div class="float-card float-insight">
              <span class="float-icon green"><Sparkles :size="15" /></span>
              <span><small>AI 洞察</small><strong>3 条新发现</strong></span>
            </div>

            <span class="orbit-chip chip-a">SQL</span>
            <span class="orbit-chip chip-b">BI</span>
            <span class="orbit-chip chip-c">MCP</span>
          </div>
        </div>
      </div>

      <div class="auth-card reveal reveal-card">
        <div class="card-glow" aria-hidden="true" />
        <header class="auth-card-head">
          <div class="card-brand">
            <img src="/chatbi-mark.svg" alt="" aria-hidden="true" />
            <span>智析 <em>ChatBI</em></span>
          </div>
          <span class="card-status"><i />企业级安全登录</span>
        </header>

        <div class="auth-heading">
          <h2>{{ panelTitle }}</h2>
          <p>{{ panelSubtitle }}</p>
        </div>

        <div v-if="!isSuccess" class="auth-tabs" role="tablist" aria-label="登录注册方式">
          <span
            class="auth-tab-indicator"
            :style="{ transform: `translateX(${tabIndex * 100}%)` }"
            aria-hidden="true"
          />
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            role="tab"
            class="auth-tab"
            :class="{ active: activeTab === tab.id }"
            :aria-selected="activeTab === tab.id"
            @click="switchTab(tab.id)"
          >
            <component :is="tab.icon" :size="14" />
            <span>{{ tab.label }}</span>
          </button>
        </div>

        <Transition name="auth-panel" mode="out-in">
          <div v-if="isSuccess" key="success" class="auth-success">
            <div class="success-icon"><Check :size="26" /></div>
            <p class="success-company">{{ issuedCompany }}</p>
            <p class="success-label">企业 ID（可分享给同事）</p>
            <div class="enterprise-code">
              <strong>{{ issuedCode }}</strong>
              <button type="button" class="copy-button" @click="copyCode">
                <Check v-if="copied" :size="14" />
                <Copy v-else :size="14" />
                <span>{{ copied ? "已复制" : "复制" }}</span>
              </button>
            </div>
            <p class="success-hint">
              同事选择「员工加入」，输入该企业 ID 即可自动挂接到企业名下。
            </p>
            <button type="button" class="primary-button" @click="router.push('/workspace')">
              进入工作台
              <ArrowRight :size="16" />
            </button>
          </div>

          <div v-else-if="activeTab === 'login'" key="login" class="auth-panel">
            <form class="auth-form" @submit.prevent="submitLogin">
              <label class="field">
                <span class="field-label">用户名</span>
                <span class="field-control">
                  <UserRound :size="16" class="field-icon" />
                  <input
                    v-model="loginForm.username"
                    type="text"
                    autocomplete="username"
                    placeholder="请输入用户名"
                    required
                  />
                </span>
              </label>
              <label class="field">
                <span class="field-label">密码</span>
                <span class="field-control">
                  <LockKeyhole :size="16" class="field-icon" />
                  <input
                    v-model="loginForm.password"
                    :type="showPassword ? 'text' : 'password'"
                    autocomplete="current-password"
                    placeholder="请输入密码"
                    required
                  />
                  <button
                    type="button"
                    class="field-action"
                    :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                    @click="showPassword = !showPassword"
                  >
                    <EyeOff v-if="showPassword" :size="15" />
                    <Eye v-else :size="15" />
                  </button>
                </span>
              </label>

              <div v-if="errorMessage" class="form-error" role="alert">
                <AlertCircle :size="15" />
                <span>{{ errorMessage }}</span>
              </div>

              <button type="submit" class="primary-button" :disabled="submitting">
                <LoaderCircle v-if="submitting" :size="16" class="spin" />
                <span>{{ submitting ? "登录中…" : "登录工作台" }}</span>
                <ArrowRight v-if="!submitting" :size="16" />
              </button>

              <p class="form-footnote">
                还没有账号？
                <button type="button" @click="switchTab('enterprise')">
                  企业入驻 <ChevronRight :size="12" />
                </button>
                或
                <button type="button" @click="switchTab('employee')">
                  员工加入 <ChevronRight :size="12" />
                </button>
              </p>
            </form>
          </div>

          <div v-else-if="activeTab === 'enterprise'" key="enterprise" class="auth-panel">
            <form class="auth-form enterprise-form" @submit.prevent="submitEnterprise">
              <label class="field field-wide">
                <span class="field-label">公司全称 <em>*</em></span>
                <span class="field-control">
                  <Building2 :size="16" class="field-icon" />
                  <input
                    v-model="enterpriseForm.company_name"
                    type="text"
                    placeholder="请输入营业执照上的公司全称"
                    maxlength="200"
                    required
                  />
                </span>
              </label>

              <div class="field-row">
                <label class="field">
                  <span class="field-label">所属行业</span>
                  <span class="field-control">
                    <select v-model="enterpriseForm.industry">
                      <option value="">请选择行业</option>
                      <option v-for="item in industryOptions" :key="item" :value="item">{{ item }}</option>
                    </select>
                  </span>
                </label>
                <label class="field">
                  <span class="field-label">企业规模</span>
                  <span class="field-control">
                    <select v-model="enterpriseForm.company_size">
                      <option value="">请选择规模</option>
                      <option v-for="item in sizeOptions" :key="item" :value="item">{{ item }}</option>
                    </select>
                  </span>
                </label>
              </div>

              <div class="field-row">
                <label class="field">
                  <span class="field-label">联系人 <em>*</em></span>
                  <span class="field-control">
                    <UserRound :size="16" class="field-icon" />
                    <input
                      v-model="enterpriseForm.contact_name"
                      type="text"
                      placeholder="联系人姓名"
                      maxlength="80"
                      required
                    />
                  </span>
                </label>
                <label class="field">
                  <span class="field-label">联系电话 <em>*</em></span>
                  <span class="field-control">
                    <Phone :size="16" class="field-icon" />
                    <input
                      v-model="enterpriseForm.contact_phone"
                      type="tel"
                      placeholder="手机或座机"
                      maxlength="40"
                      required
                    />
                  </span>
                </label>
              </div>

              <label class="field field-wide">
                <span class="field-label">联系邮箱</span>
                <span class="field-control">
                  <Mail :size="16" class="field-icon" />
                  <input
                    v-model="enterpriseForm.contact_email"
                    type="email"
                    placeholder="用于接收企业 ID（选填）"
                    maxlength="200"
                  />
                </span>
              </label>

              <div class="form-divider"><span>管理员账号</span></div>

              <div class="field-row">
                <label class="field">
                  <span class="field-label">管理员姓名 <em>*</em></span>
                  <span class="field-control">
                    <input
                      v-model="enterpriseForm.display_name"
                      type="text"
                      placeholder="显示名称"
                      maxlength="80"
                      required
                    />
                  </span>
                </label>
                <label class="field">
                  <span class="field-label">登录用户名 <em>*</em></span>
                  <span class="field-control">
                    <input
                      v-model="enterpriseForm.username"
                      type="text"
                      autocomplete="username"
                      placeholder="3-32 位字母或数字"
                      maxlength="32"
                      required
                    />
                  </span>
                </label>
              </div>

              <label class="field field-wide">
                <span class="field-label">登录密码 <em>*</em></span>
                <span class="field-control">
                  <LockKeyhole :size="16" class="field-icon" />
                  <input
                    v-model="enterpriseForm.password"
                    :type="showPassword ? 'text' : 'password'"
                    autocomplete="new-password"
                    placeholder="至少 8 位字符"
                    minlength="8"
                    maxlength="64"
                    required
                  />
                  <button
                    type="button"
                    class="field-action"
                    :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                    @click="showPassword = !showPassword"
                  >
                    <EyeOff v-if="showPassword" :size="15" />
                    <Eye v-else :size="15" />
                  </button>
                </span>
              </label>

              <div v-if="errorMessage" class="form-error" role="alert">
                <AlertCircle :size="15" />
                <span>{{ errorMessage }}</span>
              </div>

              <button type="submit" class="primary-button" :disabled="submitting">
                <LoaderCircle v-if="submitting" :size="16" class="spin" />
                <span>{{ submitting ? "提交中…" : "提交申请并获取企业 ID" }}</span>
                <ArrowRight v-if="!submitting" :size="16" />
              </button>

              <p class="form-tip">
                <ShieldCheck :size="13" />
                提交后系统自动分配企业 ID，管理员将立即获得登录权限。
              </p>
            </form>
          </div>

          <div v-else key="employee" class="auth-panel">
            <form class="auth-form" @submit.prevent="submitEmployee">
              <label class="field">
                <span class="field-label">企业 ID <em>*</em></span>
                <span class="field-control">
                  <Building2 :size="16" class="field-icon" />
                  <input
                    :value="employeeForm.enterprise_code"
                    type="text"
                    class="code-input"
                    placeholder="ZX-XXXXXX"
                    maxlength="20"
                    autocomplete="off"
                    required
                    @input="normalizeCode"
                  />
                </span>
                <span class="field-hint">由企业管理员完成入驻后提供，格式如 ZX-8F3K2M</span>
              </label>

              <div class="field-row">
                <label class="field">
                  <span class="field-label">姓名 <em>*</em></span>
                  <span class="field-control">
                    <UserRound :size="16" class="field-icon" />
                    <input
                      v-model="employeeForm.display_name"
                      type="text"
                      placeholder="显示名称"
                      maxlength="80"
                      required
                    />
                  </span>
                </label>
                <label class="field">
                  <span class="field-label">用户名 <em>*</em></span>
                  <span class="field-control">
                    <input
                      v-model="employeeForm.username"
                      type="text"
                      autocomplete="username"
                      placeholder="3-32 位字母或数字"
                      maxlength="32"
                      required
                    />
                  </span>
                </label>
              </div>

              <label class="field">
                <span class="field-label">登录密码 <em>*</em></span>
                <span class="field-control">
                  <LockKeyhole :size="16" class="field-icon" />
                  <input
                    v-model="employeeForm.password"
                    :type="showPassword ? 'text' : 'password'"
                    autocomplete="new-password"
                    placeholder="至少 8 位字符"
                    minlength="8"
                    maxlength="64"
                    required
                  />
                  <button
                    type="button"
                    class="field-action"
                    :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                    @click="showPassword = !showPassword"
                  >
                    <EyeOff v-if="showPassword" :size="15" />
                    <Eye v-else :size="15" />
                  </button>
                </span>
              </label>

              <div v-if="errorMessage" class="form-error" role="alert">
                <AlertCircle :size="15" />
                <span>{{ errorMessage }}</span>
              </div>

              <button type="submit" class="primary-button" :disabled="submitting">
                <LoaderCircle v-if="submitting" :size="16" class="spin" />
                <span>{{ submitting ? "加入中…" : "加入企业并进入工作台" }}</span>
                <ArrowRight v-if="!submitting" :size="16" />
              </button>

              <p class="form-footnote">
                还没有企业 ID？
                <button type="button" @click="switchTab('enterprise')">
                  申请企业入驻 <ChevronRight :size="12" />
                </button>
              </p>
            </form>
          </div>
        </Transition>

        <footer class="auth-card-foot">
          <span><ShieldCheck :size="13" />数据仅用于企业内部分析</span>
          <span class="foot-dot">·</span>
          <span>智析 ChatBI 2026</span>
        </footer>
      </div>
    </div>
  </section>
</template>
