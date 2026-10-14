<template>
  <div class="empty-state">
    <div class="empty-state__icon"><UiIcon :name="icon" /></div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ icon?: string; title: string; description: string }>(), { icon: 'cube' });
</script>

<style scoped>
.empty-state { display: grid; justify-items: center; max-width: 390px; margin: auto; padding: 2.5rem 1.25rem; text-align: center; }
.empty-state__icon { display: grid; width: 3rem; height: 3rem; place-items: center; border: 1px solid var(--border); border-radius: .9rem; background: var(--surface-soft); color: var(--violet-600); }
.empty-state__icon :deep(svg) { width: 1.25rem; }
.empty-state h3 { margin: 1rem 0 .35rem; font-size: .983rem; }
.empty-state p { margin: 0 0 1rem; color: var(--ink-600); font-size: .925rem; line-height: 1.6; }
</style>
