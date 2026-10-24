<template>
  <NuxtLink :to="to" class="brand-logo" :class="{ 'brand-logo--compact': compact }" :aria-label="t('nav.logoHome')">
    <img src="/brand/silicium-icon.svg" alt="" width="44" height="44" class="brand-logo__mark">
    <span v-if="!compact" class="brand-logo__name">Silicium</span>
  </NuxtLink>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ to?: string; compact?: boolean }>(), { to: '/', compact: false });
const { t } = useI18n();
</script>

<style scoped>
.brand-logo { display: inline-flex; align-items: center; gap: .68rem; min-width: max-content; }
.brand-logo__mark { width: 2.75rem; height: 2.75rem; flex: none; object-fit: contain; }
.brand-logo__name { color: var(--ink-950); font-size: 1.2rem; font-weight: 800; letter-spacing: -.04em; }
.brand-logo--compact .brand-logo__mark { width: 2rem; height: 2rem; }
</style>
