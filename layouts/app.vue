<template>
  <div class="app-layout"><AppSidebar /><div class="app-layout__column"><AppHeader /><main class="app-layout__main"><slot /></main></div><AppMobileNav /></div>
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
.app-layout{min-height:100vh;background:radial-gradient(circle at 90% 2%,rgba(24,181,165,.05),transparent 20%),var(--paper)}.app-layout__column{min-width:0;margin-left:245px}.app-layout__main{width:min(100%,1320px);margin:0 auto;padding:2rem}
@media(max-width:840px){.app-layout__column{margin-left:0}.app-layout__main{padding:1.25rem .75rem calc(5.5rem + env(safe-area-inset-bottom))}}
</style>
