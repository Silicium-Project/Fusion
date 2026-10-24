<template>
  <header class="app-header">
    <div class="app-header__mobile-brand"><BrandLogo /></div>
    <div class="app-header__context"><span>{{ section }}</span><strong>{{ title }}</strong></div>
    <div class="app-header__actions">
      <ReleaseBadge :channel="release.channel" :version="release.version" :build="release.build" />
      <span class="app-header__status" :class="`app-header__status--${serviceTone}`"><i></i> {{ serviceLabel }}</span>
      <LocaleSwitcher />
      <NuxtLink to="/profile" class="app-header__avatar" :aria-label="t('nav.openAccount')">{{ initials }}</NuxtLink>
    </div>
  </header>
</template>

<script setup lang="ts">
import { statusLabel, statusTone } from '~/utils/format';
const route = useRoute();
const { t } = useI18n();
const { initials } = useSession();
const { status, refresh } = useSystemStatus();
/** Section and title of each page, as catalog keys. */
const labels: Record<string, [string, string]> = {
  '/dashboard': ['nav.yourSpace', 'nav.home'], '/jobs': ['nav.yourSpace', 'nav.projects'], '/jobs/new': ['nav.projects', 'common.newJob'],
  '/network': ['nav.resources', 'nav.networkHealth'], '/nodes': ['nav.resources', 'nav.machines'], '/workloads': ['nav.resources', 'nav.workloads'],
  '/download': ['nav.resources', 'nav.downloadNode'], '/profile': ['nav.account', 'nav.settings'],
  '/workers/overview': ['observability.worker.kicker', 'observability.worker.nav'],
};
const matched = computed(() => route.path.startsWith('/jobs/') && route.path !== '/jobs/new' ? ['nav.projects', 'nav.projectFollowUp'] : labels[route.path] || ['', 'nav.workspace']);
const section = computed(() => matched.value[0] ? t(matched.value[0]) : 'Silicium');
const title = computed(() => t(matched.value[1]));
const serviceStatus = computed(() => status.value?.status || 'unknown');
const serviceLabel = computed(() => statusLabel(serviceStatus.value));
const serviceTone = computed(() => statusTone(serviceStatus.value));
const config = useRuntimeConfig();
const release = computed(() => ({
  channel: status.value?.release?.release_channel || String(config.public.releaseChannel || 'dev'),
  version: status.value?.release?.release_version || String(config.public.releaseVersion || 'unknown'),
  build: status.value?.release?.release_build || String(config.public.releaseBuild || 'local'),
}));
onMounted(() => { if (!status.value) refresh().catch(() => undefined); });
</script>

<style scoped>
@media(max-width:400px){.app-header__mobile-brand :deep(.brand-logo__name){display:none}}

.app-header{position:sticky;top:0;z-index:30;display:flex;min-height:4.65rem;align-items:center;justify-content:space-between;gap:1rem;padding:.65rem clamp(1.25rem,3vw,2.75rem);border-bottom:1px solid var(--border);background:rgba(251,253,255,.88);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px)}
.app-header__mobile-brand{display:none}.app-header__context{display:flex;align-items:center;gap:.7rem;min-width:0}.app-header__context span{color:var(--ink-500);font-size:.9375rem}.app-header__context span::after{margin-left:.7rem;color:var(--ink-300);content:'/'} .app-header__context strong{font-size:.9375rem;font-weight:500}
.app-header__actions{display:flex;align-items:center;gap:.75rem}.app-header__status{display:inline-flex;align-items:center;gap:.45rem;color:var(--ink-600);font-size:.9375rem}.app-header__status i{width:.35rem;height:.35rem;flex:none;border-radius:50%;background:var(--green-600)}.app-header__status--warning i{background:var(--amber-600)}.app-header__status--danger i{background:var(--red-600)}.app-header__status--neutral i{background:var(--ink-400)}
.app-header__avatar{display:grid;width:2.75rem;height:2.75rem;place-items:center;border:1px solid var(--border);border-radius:50%;background:var(--mint-100);color:var(--mint-800);font-size:.9375rem;font-weight:600}.app-header__actions :deep(.release-badge){font-size:.9375rem}.app-header__actions :deep(.release-badge small){display:none}
@media(max-width:1050px){.app-header__status{display:none}}
@media(max-width:840px){.app-header{min-height:4.5rem;padding:.65rem 1rem}.app-header__actions{gap:.5rem}.app-header__mobile-brand{display:block}.app-header__context{display:none}.app-header__actions :deep(.release-badge){display:none}.app-header__mobile-brand :deep(.brand-logo__name){font-size:1.05rem}}
</style>
