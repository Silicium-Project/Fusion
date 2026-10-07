<template>
  <header class="app-header">
    <div class="app-header__mobile-brand"><BrandLogo /></div>
    <div class="app-header__context"><span>{{ section }}</span><strong>{{ title }}</strong></div>
    <div class="app-header__actions">
      <ReleaseBadge :channel="release.channel" :version="release.version" :build="release.build" />
      <span class="app-header__status" :class="`app-header__status--${serviceTone}`"><i></i> {{ serviceLabel }}</span>
      <LocaleSwitcher />
      <UiButton to="/jobs/new" icon="upload" size="small">{{ t('common.newJob') }}</UiButton>
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
};
const matched = computed(() => route.path.startsWith('/jobs/') && route.path !== '/jobs/new' ? ['nav.projects', 'nav.projectFollowUp'] : labels[route.path] || ['', 'nav.workspace']);
const section = computed(() => matched.value[0] ? t(matched.value[0]) : 'Silicium');
const title = computed(() => t(matched.value[1]));
const serviceStatus = computed(() => status.value?.status || 'operational');
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
.app-header { position:sticky;top:0;z-index:30;display:flex;height:5.3rem;align-items:center;justify-content:space-between;gap:1rem;padding:0 2rem;border-bottom:1px solid rgba(11,21,35,.07);background:rgba(242,245,243,.7);-webkit-backdrop-filter:blur(24px) saturate(1.3);backdrop-filter:blur(24px) saturate(1.3) }
.app-header__mobile-brand{display:none}.app-header__context span,.app-header__context strong{display:block}.app-header__context span{color:var(--ink-500);font-size:.64rem;font-weight:760}.app-header__context strong{margin-top:.14rem;font-family:var(--font-display);font-size:.92rem;letter-spacing:-.025em}.app-header__actions{display:flex;align-items:center;gap:.6rem}.app-header__status{display:inline-flex;align-items:center;gap:.42rem;margin-right:.4rem;color:var(--ink-600);font-size:.68rem;font-weight:680}.app-header__status i{width:.42rem;height:.42rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 4px var(--mint-100),0 0 16px rgba(18,191,174,.4)}.app-header__status--warning i{background:var(--amber-600);box-shadow:0 0 0 4px var(--amber-100),0 0 16px rgba(231,159,38,.32)}.app-header__status--danger i{background:var(--red-600);box-shadow:0 0 0 4px var(--red-100),0 0 16px rgba(196,71,71,.32)}.app-header__status--neutral i{background:var(--ink-400);box-shadow:0 0 0 4px var(--ink-100)}.app-header__avatar{display:grid;width:2.3rem;height:2.3rem;place-items:center;border:1px solid rgba(255,255,255,.82);border-radius:.72rem;background:rgba(255,255,255,.76);box-shadow:inset 0 0 0 1px var(--border),var(--shadow-xs);color:var(--violet-600);font-size:.66rem;font-weight:850;backdrop-filter:blur(14px)}
@media (min-width:841px) and (max-width:1180px){.app-header{padding-inline:clamp(1rem,3.2vw,2rem)}}
@media(max-width:840px){.app-header{height:4.2rem;padding:0 .8rem}.app-header__actions{gap:.45rem}.app-header__mobile-brand{display:block}.app-header__context{display:none}.app-header__status,.app-header__actions :deep(.ui-button){display:none}.app-header__actions :deep(.release-badge){display:none}}
</style>
