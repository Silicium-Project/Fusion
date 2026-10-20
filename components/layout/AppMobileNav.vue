<template>
  <nav class="mobile-nav" :aria-label="t('nav.mobileNavigation')">
    <NuxtLink v-for="item in items" :key="item.to" :to="item.to" :aria-label="item.label"><UiIcon :name="item.icon"/><span>{{ item.shortLabel || item.label }}</span></NuxtLink>
  </nav>
</template>

<script setup lang="ts">
const { t } = useI18n();
const items = computed(() => [
  { label: t('nav.home'), to: '/dashboard', icon: 'overview' }, { label: t('nav.projects'), shortLabel: t('nav.projectsShort'), to: '/jobs', icon: 'jobs' },
  { label: t('observability.worker.nav'), shortLabel: t('observability.worker.shortNav'), to: '/workers/overview', icon: 'processor' }, { label: t('nav.network'), to: '/network', icon: 'network' },
]);
</script>

<style scoped>
.mobile-nav{display:none}.mobile-nav a>span{max-width:100%;min-width:0;text-align:center;overflow-wrap:anywhere;line-height:1.3}
@media(max-width:840px){.mobile-nav{position:fixed;inset:auto 1rem max(.75rem,env(safe-area-inset-bottom));z-index:45;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));min-height:4.2rem;padding:.3rem;border:1px solid var(--glass-edge);border-radius:1.3rem;background:rgba(255,255,255,.94);box-shadow:var(--glass-inset),0 5px 24px rgba(29,61,103,.08);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px)}.mobile-nav a{display:flex;min-height:3.5rem;align-items:center;justify-content:center;flex-direction:column;gap:.3rem;border-radius:1rem;color:var(--ink-600);font-size:.9375rem;font-weight:500}.mobile-nav svg{width:1.2rem;height:1.2rem}.mobile-nav a.router-link-active{background:#edf5ff;color:var(--mint-700)}}
</style>
