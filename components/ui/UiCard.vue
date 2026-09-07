<template>
  <section v-tilt="interactive" class="ui-card" :class="{ 'ui-card--padded': padded, 'ui-card--interactive tilt-surface': interactive }">
    <span v-if="interactive" class="ui-card__glow" aria-hidden="true"></span>
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
withDefaults(defineProps<{ title?: string; description?: string; padded?: boolean; interactive?: boolean }>(), { padded: false, interactive: false });
</script>

<style scoped>
.ui-card { position:relative;isolation:isolate;overflow: hidden; border: 1px solid var(--glass-edge); border-radius: var(--radius-lg); background: var(--glass-card); box-shadow: var(--glass-inset), var(--glass-shadow); -webkit-backdrop-filter:blur(22px) saturate(1.22); backdrop-filter:blur(22px) saturate(1.22); }
.ui-card::before{position:absolute;inset:0;background:radial-gradient(circle at var(--spatial-light-x,50%) var(--spatial-light-y,50%),rgba(255,255,255,.32),transparent 34%),var(--glass-refraction);opacity:.24;pointer-events:none;content:''}
.ui-card--interactive:hover{box-shadow:inset 0 0 0 1px rgba(18,191,174,.18),var(--shadow-lg)}
.ui-card__glow{position:absolute;z-index:0;inset:-1px;border-radius:inherit;opacity:0;background:radial-gradient(circle at var(--glow-x) var(--glow-y),rgba(255,255,255,.92),rgba(18,191,174,.1) 24%,transparent 52%);pointer-events:none;transition:opacity .35s ease}.ui-card--interactive:hover>.ui-card__glow{opacity:1}.ui-card>*:not(.ui-card__glow){position:relative;z-index:1}
.ui-card--padded { padding: 1.25rem; }
.ui-card__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1.15rem 1.25rem; border-bottom: 1px solid var(--border); }
.ui-card__body { min-width: 0; }
@media (max-width: 640px) { .ui-card__header { align-items: stretch; flex-direction: column; } }
@supports not (backdrop-filter: blur(1px)) { .ui-card { background: var(--surface); } }
</style>
