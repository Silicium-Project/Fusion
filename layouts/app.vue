<template>
  <div class="app-layout"><AppSidebar /><div class="app-layout__column"><AppHeader /><AppMobileNav /><main class="app-layout__main"><slot /></main></div></div>
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
.app-layout{position:relative;min-height:100vh;overflow:clip;background:var(--paper)}.app-layout__aura{display:none}.app-layout__column{position:relative;min-width:0;margin-left:230px}.app-layout__main{width:min(100%,1440px);margin:auto;padding:2.5rem clamp(1.25rem,3vw,2.75rem) 4rem}
@media(min-width:841px) and (max-width:1180px){.app-layout__column{margin-left:88px}}
@media(max-width:840px){.app-layout__column{margin-left:0}.app-layout__main{padding:1.6rem clamp(12px,4vw,20px) calc(7rem + env(safe-area-inset-bottom))}}
</style>
