<template>
  <section class="ui-card" :class="{ 'ui-card--padded': padded }">
    <header v-if="$slots.header || title" class="ui-card__header">
      <slot name="header">
        <div><h2 class="section-title">{{ title }}</h2><p v-if="description" class="section-description">{{ description }}</p></div>
      </slot>
      <slot name="actions" />
    </header>
    <div :class="{ 'ui-card__body': $slots.header || title }"><slot /></div>
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ title?: string; description?: string; padded?: boolean }>(), { padded: false });
</script>

<style scoped>
.ui-card { overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-lg); background: rgba(255,255,255,.93); box-shadow: var(--shadow-sm); }
.ui-card--padded { padding: 1.25rem; }
.ui-card__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1.15rem 1.25rem; border-bottom: 1px solid var(--border); }
.ui-card__body { min-width: 0; }
@media (max-width: 640px) { .ui-card__header { align-items: stretch; flex-direction: column; } }
</style>
