<template>
  <section
    class="ui-card"
    :class="{ 'ui-card--padded': padded, 'ui-card--interactive': interactive }"
  >
    <span v-if="interactive" class="ui-card__glow" aria-hidden="true"></span>
    <header v-if="$slots.header || title" class="ui-card__header">
      <slot name="header">
        <div>
          <h2 class="section-title">{{ title }}</h2>
          <p v-if="description" class="section-description">{{ description }}</p>
        </div>
      </slot>
      <slot name="actions" />
    </header>
    <div :class="{ 'ui-card__body': $slots.header || title }"><slot /></div>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{ title?: string; description?: string; padded?: boolean; interactive?: boolean }>(),
  { padded: false, interactive: false },
);
</script>

<style scoped>
.ui-card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  min-width: 0;
  border: 1px solid var(--glass-edge);
  border-radius: var(--radius-lg);
  background: var(--glass-card);
  box-shadow: var(--glass-inset), var(--glass-shadow);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
}
.ui-card::before,
.ui-card__glow {
  display: none;
}
.ui-card--interactive:hover {
  border-color: #cadaee;
}
.ui-card > *:not(.ui-card__glow) {
  position: relative;
  z-index: 1;
}
.ui-card--padded {
  padding: 1.5rem;
}
.ui-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 1.35rem 1.5rem;
  border-bottom: 1px solid var(--border);
}
.ui-card__body {
  min-width: 0;
}
@media (max-width: 640px) {
  .ui-card--padded {
    padding: 1.1rem;
  }
  .ui-card__header {
    align-items: stretch;
    flex-direction: column;
    padding: 1.1rem;
  }
}
@supports not (backdrop-filter: blur(1px)) {
  .ui-card {
    background: var(--surface);
  }
}
</style>
