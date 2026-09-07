<template>
  <div v-spatial class="app-layout"><div class="app-layout__aura" aria-hidden="true"></div><AppSidebar /><div class="app-layout__column"><AppHeader /><AppMobileNav /><main class="app-layout__main"><slot /></main></div></div>
</template>

<script setup lang="ts">
const { loadUser } = useSession();
onMounted(async () => {
  try {
    await loadUser();
  } catch {
    await navigateTo('/auth?mode=login');
  }
});
</script>

<style scoped>
.app-layout{position:relative;min-height:100vh;overflow:hidden;overflow:clip;background:linear-gradient(155deg,rgba(255,255,255,.48),transparent 42%),var(--paper)}.app-layout__aura{position:fixed;top:-18rem;right:-14rem;width:42rem;height:42rem;border-radius:50%;background:radial-gradient(circle,rgba(18,191,174,.1),transparent 68%);pointer-events:none;animation:app-aura 14s ease-in-out infinite}.app-layout__column{position:relative;z-index:1;min-width:0;margin-left:260px}.app-layout__main{width:min(100%,1320px);margin:0 auto;padding:clamp(1.25rem,2.7vw,2.2rem) clamp(1rem,3vw,2.6rem) clamp(2.2rem,4vw,3.5rem)}@keyframes app-aura{50%{transform:translate3d(-4rem,5rem,0) scale(1.08)}}
@media (min-width:841px) and (max-width:1180px){.app-layout__column{margin-left:94px}.app-layout__main{padding-inline:clamp(1rem,3.2vw,2rem)}}
@media(max-width:840px){.app-layout__column{margin-left:0}.app-layout__main{padding:1.1rem .75rem 2.35rem}}
</style>
