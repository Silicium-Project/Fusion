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
      <UiButton to="/jobs/new" icon="upload" :title="t('common.newJob')" :aria-label="t('common.newJob')"><span class="app-sidebar__network-label">{{ t('common.newJob') }}</span></UiButton>
      <NuxtLink to="/profile" class="app-sidebar__profile"><span>{{ initials }}</span><div><strong>{{ displayName }}</strong><small>{{ user?.email }}</small></div><UiIcon name="chevron"/></NuxtLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
const { user, displayName, initials } = useSession();
const { t } = useI18n();
const primary = computed(() => [{ label: t('nav.home'), to: '/dashboard', icon: 'overview' }, { label: t('nav.projects'), to: '/jobs', icon: 'jobs' }]);
const infrastructure = computed(() => [{ label: t('nav.machines'), to: '/nodes', icon: 'nodes' }, { label: t('nav.workloads'), to: '/workloads', icon: 'layers' }, { label: t('nav.downloadNode'), to: '/download', icon: 'download' }, { label: t('nav.networkHealth'), to: '/network', icon: 'network' }]);
</script>

<style scoped>
.app-sidebar { position:fixed;inset:.75rem auto .75rem .75rem;z-index:40;display:flex;width:245px;overflow:hidden;flex-direction:column;border:1px solid var(--glass-edge);border-radius:1.35rem;background:var(--glass-card);box-shadow:var(--glass-inset),var(--glass-shadow);backdrop-filter:blur(26px) saturate(1.3) }
.app-sidebar__brand { display:flex;height:4.8rem;align-items:center;padding:0 1.35rem;border-bottom:1px solid var(--border) }
.app-sidebar__nav { display:grid;gap:.3rem;padding:1.3rem .75rem }.app-sidebar__nav p{margin:1rem .65rem .4rem;color:var(--ink-500);font-size:.62rem;font-weight:820;letter-spacing:.12em;text-transform:uppercase}.app-sidebar__nav p:first-child{margin-top:0}.app-sidebar__nav a{display:flex;min-height:2.8rem;align-items:center;gap:.75rem;padding:0 .8rem;border-radius:.78rem;color:var(--ink-600);font-size:.8rem;font-weight:700;transition:background-color .25s,color .25s,transform .3s var(--ease-spring),box-shadow .25s}.app-sidebar__nav a svg{width:1.08rem;height:1.08rem}.app-sidebar__nav a:hover{transform:translateX(3px);background:rgba(255,255,255,.72);color:var(--ink-950)}.app-sidebar__nav a.router-link-active{background:rgba(255,255,255,.92);color:var(--ink-950);box-shadow:inset 0 0 0 1px rgba(18,191,174,.1),var(--shadow-sm)}.app-sidebar__nav a.router-link-active svg{color:var(--mint-600)}
.app-sidebar__bottom { display:grid;gap:.8rem;margin-top:auto;padding:1rem;border-top:1px solid var(--border) }.app-sidebar__profile{display:grid;grid-template-columns:2.15rem minmax(0,1fr) .8rem;align-items:center;gap:.6rem;padding:.45rem;border-radius:.75rem}.app-sidebar__profile>span{display:grid;width:2.15rem;height:2.15rem;place-items:center;border-radius:.62rem;background:var(--violet-100);color:var(--violet-600);font-size:.68rem;font-weight:800}.app-sidebar__profile strong,.app-sidebar__profile small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-sidebar__profile strong{font-size:.69rem}.app-sidebar__profile small{margin-top:.18rem;color:var(--ink-500);font-size:.59rem}.app-sidebar__profile svg{width:.8rem;color:var(--ink-500)}
@media (min-width:841px) and (max-width:1180px){.app-sidebar{width:76px}.app-sidebar__brand{justify-content:center;padding:0}.app-sidebar__brand :deep(.brand-logo){gap:0}.app-sidebar__brand :deep(.brand-logo__name){display:none}.app-sidebar__nav{padding-inline:.55rem}.app-sidebar__nav p{height:1px;margin:.85rem .3rem .45rem;overflow:hidden;font-size:0;border-top:1px solid var(--border)}.app-sidebar__nav a{justify-content:center;gap:0;padding:0}.app-sidebar__nav a:hover{transform:translateY(-2px)}.app-sidebar__nav a>span{display:none}.app-sidebar__bottom{padding:.65rem}.app-sidebar__bottom :deep(.ui-button){width:100%;min-width:0;padding-inline:0}.app-sidebar__bottom :deep(.ui-button__icon){margin:0}.app-sidebar__bottom :deep(.app-sidebar__network-label){display:none}.app-sidebar__profile{display:flex;justify-content:center;padding:.35rem}.app-sidebar__profile>div,.app-sidebar__profile>svg{display:none}}
@media(max-width:840px){.app-sidebar{display:none}}
</style>
