<template>
  <nav class="mobile-nav" :aria-label="t('nav.mobileNavigation')">
    <NuxtLink v-for="item in items" :key="item.to" :to="item.to" :aria-label="item.label"><UiIcon :name="item.icon"/><span>{{ item.shortLabel || item.label }}</span></NuxtLink>
  </nav>
</template>

<script setup lang="ts">
const { t } = useI18n();
const items = computed(() => [
  { label: t('nav.home'), to: '/dashboard', icon: 'overview' }, { label: t('nav.projects'), shortLabel: t('nav.projectsShort'), to: '/jobs', icon: 'jobs' },
  { label: t('common.newJob'), shortLabel: t('nav.newShort'), to: '/jobs/new', icon: 'upload' }, { label: t('nav.machines'), to: '/nodes', icon: 'nodes' }, { label: t('nav.account'), to: '/profile', icon: 'account' },
]);
</script>

<style scoped>
.mobile-nav{display:none}
@media(max-width:840px){
  .mobile-nav{display:grid;height:3.65rem;grid-template-columns:repeat(5,1fr);margin:0 .75rem;padding:0 .2rem;border:1px solid var(--glass-edge);border-radius:1rem;background:var(--glass-card);box-shadow:var(--glass-inset),0 12px 30px rgba(17,27,42,.1);-webkit-backdrop-filter:blur(24px) saturate(1.3);backdrop-filter:blur(24px) saturate(1.3)}
  .mobile-nav a{display:flex;align-items:center;justify-content:center;flex-direction:column;gap:.2rem;color:var(--ink-500);font-size:.54rem;font-weight:760;transition:color .25s,transform .25s var(--ease-spring)}
  .mobile-nav a:active{transform:scale(.92)}
  .mobile-nav svg{width:1rem;height:1rem}
  .mobile-nav a.router-link-active{color:var(--mint-700)}
  .mobile-nav a:nth-child(3) svg{width:1.65rem;height:1.65rem;padding:.39rem;border-radius:.62rem;background:linear-gradient(145deg,var(--ink-800),var(--ink-950));color:white;box-shadow:inset 0 1px 0 rgba(255,255,255,.18),0 8px 16px rgba(11,21,35,.18)}
}
@supports not (backdrop-filter: blur(1px)) { @media(max-width:840px){ .mobile-nav { background: var(--surface); } } }
</style>
