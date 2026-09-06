<template>
  <nav class="mobile-nav" aria-label="Navigation mobile de l’application">
    <NuxtLink v-for="item in items" :key="item.to" :to="item.to"><UiIcon :name="item.icon"/><span>{{ item.label }}</span></NuxtLink>
  </nav>
</template>

<script setup lang="ts">
const items = [
  { label: 'Accueil', to: '/dashboard', icon: 'overview' }, { label: 'Tâches', to: '/jobs', icon: 'jobs' },
  { label: 'Créer', to: '/jobs/new', icon: 'plus' }, { label: 'Réseau', to: '/network', icon: 'network' }, { label: 'Compte', to: '/profile', icon: 'account' },
];
</script>

<style scoped>
.mobile-nav{display:none}@media(max-width:840px){.mobile-nav{position:fixed;right:0;bottom:0;left:0;z-index:50;display:grid;height:calc(4.35rem + env(safe-area-inset-bottom));grid-template-columns:repeat(5,1fr);padding:0 .25rem env(safe-area-inset-bottom);border-top:1px solid var(--border);background:rgba(255,255,255,.96);box-shadow:0 -10px 30px rgba(17,27,42,.07);backdrop-filter:blur(16px)}.mobile-nav a{display:flex;align-items:center;justify-content:center;flex-direction:column;gap:.25rem;color:var(--ink-500);font-size:.55rem;font-weight:750}.mobile-nav svg{width:1.05rem;height:1.05rem}.mobile-nav a.router-link-active{color:var(--mint-700)}.mobile-nav a:nth-child(3) svg{width:1.6rem;height:1.6rem;padding:.38rem;border-radius:.55rem;background:var(--ink-950);color:white}}
</style>
