<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__brand"><BrandLogo /></div>
    <nav class="app-sidebar__nav" :aria-label="t('nav.appNavigation')">
      <p>{{ t('nav.yourSpace') }}</p>
      <NuxtLink v-for="item in primary" :key="item.to" :to="item.to" :title="item.label" :aria-label="item.label"><UiIcon :name="item.icon"/><span>{{ item.label }}</span></NuxtLink>
      <p>{{ t('nav.resources') }}</p>
      <NuxtLink v-for="item in infrastructure" :key="item.to" :to="item.to" :title="item.label" :aria-label="item.label"><UiIcon :name="item.icon"/><span>{{ item.label }}</span></NuxtLink>
    </nav>
    <div class="app-sidebar__bottom">
      <NuxtLink to="/profile" class="app-sidebar__profile"><span>{{ initials }}</span><div><strong>{{ displayName }}</strong><small>{{ user?.email }}</small></div><UiIcon name="chevron"/></NuxtLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
const { user, displayName, initials } = useSession();
const { t } = useI18n();
const primary = computed(() => [{ label: t('nav.home'), to: '/dashboard', icon: 'overview' }, { label: t('nav.projects'), to: '/jobs', icon: 'jobs' }, { label: t('observability.worker.nav'), to: '/workers/overview', icon: 'processor' }]);
const infrastructure = computed(() => [{ label: t('observability.worker.nodes'), to: '/nodes', icon: 'nodes' }, { label: t('nav.workloads'), to: '/workloads', icon: 'layers' }, { label: t('nav.downloadNode'), to: '/download', icon: 'download' }, { label: t('nav.networkHealth'), to: '/network', icon: 'network' }]);
</script>

<style scoped>
.app-sidebar{overflow-y:auto;position:fixed;inset:0 auto 0 0;z-index:40;display:flex;width:230px;flex-direction:column;border-right:1px solid var(--border);background:rgba(255,255,255,.8);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px)}
.app-sidebar__brand{display:flex;min-height:4.65rem;align-items:center;padding:0 1.4rem;border-bottom:1px solid var(--border)}
.app-sidebar__nav{display:grid;gap:.3rem;padding:1.5rem .85rem}.app-sidebar__nav p{margin:1.5rem .7rem .55rem;color:var(--ink-500);font-size:1rem;font-weight:550;letter-spacing:.09em;text-transform:uppercase}.app-sidebar__nav p:first-child{margin-top:0}
.app-sidebar__nav a{position:relative;display:flex;min-height:3rem;align-items:center;gap:.75rem;padding:.7rem .8rem;border-radius:.7rem;color:var(--ink-700);font-size:1rem;font-weight:500;transition:background .2s,color .2s}.app-sidebar__nav a svg{width:1.08rem;height:1.08rem;flex:none}.app-sidebar__nav a:hover{background:#f1f6fd;color:var(--ink-950)}.app-sidebar__nav a.router-link-active{background:linear-gradient(100deg,#eaf3ff,#f3f8ff);color:var(--mint-700);box-shadow:inset 0 1px 0 #fff}.app-sidebar__nav a.router-link-active::before{position:absolute;inset:.75rem auto .75rem 0;width:2px;border-radius:2px;background:var(--mint-500);content:''}
.app-sidebar__bottom{margin-top:auto;padding:1.2rem .85rem;border-top:1px solid var(--border)}.app-sidebar__profile{display:grid;grid-template-columns:2.3rem minmax(0,1fr) .8rem;align-items:center;gap:.65rem;padding:.5rem;border-radius:.75rem}.app-sidebar__profile>span{display:grid;width:2.3rem;height:2.3rem;place-items:center;border-radius:50%;background:var(--mint-100);color:var(--mint-800);font-size:.9375rem;font-weight:600}.app-sidebar__profile strong,.app-sidebar__profile small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-sidebar__profile strong{font-size:.9375rem;font-weight:550}.app-sidebar__profile small{margin-top:.2rem;color:var(--ink-500);font-size:.9375rem}.app-sidebar__profile svg{width:.8rem;color:var(--ink-500)}.app-sidebar__profile:hover{background:var(--surface-soft)}
@media(min-width:841px) and (max-width:1180px){.app-sidebar{width:88px}.app-sidebar__brand{justify-content:center;padding:0}.app-sidebar__brand :deep(.brand-logo){gap:0}.app-sidebar__brand :deep(.brand-logo__name){display:none}.app-sidebar__nav{padding-inline:.7rem}.app-sidebar__nav p{height:1px;margin:1rem .3rem .6rem;overflow:hidden;font-size:0;border-top:1px solid var(--border)}.app-sidebar__nav a{justify-content:center;padding:.8rem}.app-sidebar__nav a>span{display:none}.app-sidebar__profile{display:flex;justify-content:center}.app-sidebar__profile>div,.app-sidebar__profile>svg{display:none}}
@media(max-width:840px){.app-sidebar{display:none}}
</style>
