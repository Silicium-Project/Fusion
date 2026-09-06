<template>
  <NuxtLink :to="to" class="brand-logo" :class="{ 'brand-logo--compact': compact }" aria-label="Silicium — Accueil">
    <img src="/brand/silicium-logo.png" alt="" class="brand-logo__mark">
    <span v-if="!compact" class="brand-logo__name">Silicium</span>
  </NuxtLink>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ to?: string; compact?: boolean }>(), { to: '/', compact: false });
</script>

<style scoped>
.brand-logo { display: inline-flex; align-items: center; gap: .68rem; min-width: max-content; }
.brand-logo__mark { width: 2.15rem; height: 2.15rem; border-radius: .58rem; object-fit: cover; }
.brand-logo__name { color: var(--ink-950); font-size: 1.05rem; font-weight: 800; letter-spacing: -.04em; }
.brand-logo--compact .brand-logo__mark { width: 2rem; height: 2rem; }
</style>
