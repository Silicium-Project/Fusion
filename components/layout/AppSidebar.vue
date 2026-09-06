<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__brand"><BrandLogo /></div>
    <nav class="app-sidebar__nav" aria-label="Navigation de l’application">
      <p>Workspace</p>
      <NuxtLink v-for="item in primary" :key="item.to" :to="item.to"><UiIcon :name="item.icon"/><span>{{ item.label }}</span></NuxtLink>
      <p>Infrastructure</p>
      <NuxtLink v-for="item in infrastructure" :key="item.to" :to="item.to"><UiIcon :name="item.icon"/><span>{{ item.label }}</span></NuxtLink>
    </nav>
    <div class="app-sidebar__bottom">
      <UiButton to="/jobs/new" icon="plus">Nouvelle tâche</UiButton>
      <NuxtLink to="/profile" class="app-sidebar__profile"><span>{{ initials }}</span><div><strong>{{ displayName }}</strong><small>{{ user?.email }}</small></div><UiIcon name="chevron"/></NuxtLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
const { user, displayName, initials } = useSession();
const primary = [{ label: 'Vue d’ensemble', to: '/dashboard', icon: 'overview' }, { label: 'Tâches', to: '/jobs', icon: 'jobs' }];
const infrastructure = [{ label: 'Réseau', to: '/network', icon: 'network' }, { label: 'Nœuds', to: '/nodes', icon: 'nodes' }];
</script>

<style scoped>
.app-sidebar { position:fixed;inset:0 auto 0 0;z-index:40;display:flex;width:245px;flex-direction:column;border-right:1px solid var(--border);background:rgba(248,247,243,.95);backdrop-filter:blur(14px) }
.app-sidebar__brand { display:flex;height:4.8rem;align-items:center;padding:0 1.35rem;border-bottom:1px solid var(--border) }
.app-sidebar__nav { display:grid;gap:.25rem;padding:1.3rem .75rem }.app-sidebar__nav p{margin:1rem .65rem .35rem;color:var(--ink-500);font-size:.6rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.app-sidebar__nav p:first-child{margin-top:0}.app-sidebar__nav a{display:flex;min-height:2.65rem;align-items:center;gap:.75rem;padding:0 .75rem;border-radius:.7rem;color:var(--ink-600);font-size:.77rem;font-weight:700;transition:background-color .15s,color .15s}.app-sidebar__nav a svg{width:1.05rem;height:1.05rem}.app-sidebar__nav a:hover{background:rgba(255,255,255,.7);color:var(--ink-950)}.app-sidebar__nav a.router-link-active{background:white;color:var(--ink-950);box-shadow:var(--shadow-sm)}.app-sidebar__nav a.router-link-active svg{color:var(--mint-600)}
.app-sidebar__bottom { display:grid;gap:.8rem;margin-top:auto;padding:1rem;border-top:1px solid var(--border) }.app-sidebar__profile{display:grid;grid-template-columns:2.15rem minmax(0,1fr) .8rem;align-items:center;gap:.6rem;padding:.45rem;border-radius:.75rem}.app-sidebar__profile>span{display:grid;width:2.15rem;height:2.15rem;place-items:center;border-radius:.62rem;background:var(--violet-100);color:var(--violet-600);font-size:.68rem;font-weight:800}.app-sidebar__profile strong,.app-sidebar__profile small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.app-sidebar__profile strong{font-size:.69rem}.app-sidebar__profile small{margin-top:.18rem;color:var(--ink-500);font-size:.59rem}.app-sidebar__profile svg{width:.8rem;color:var(--ink-500)}
@media(max-width:840px){.app-sidebar{display:none}}
</style>
