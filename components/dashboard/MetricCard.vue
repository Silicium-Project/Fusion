<template>
  <article class="metric-card">
    <div class="metric-card__icon" :class="`metric-card__icon--${tone}`"><UiIcon :name="icon" /></div>
    <div><p>{{ label }}</p><strong>{{ value }}</strong><span v-if="detail">{{ detail }}</span></div>
  </article>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ label: string; value: string | number; detail?: string; icon?: string; tone?: 'mint' | 'violet' | 'amber' | 'ink' }>(), { icon: 'activity', tone: 'mint' });
</script>

<style scoped>
.metric-card { display: flex; min-height: 112px; align-items: flex-start; gap: .9rem; padding: 1.1rem; border: 1px solid var(--border); border-radius: var(--radius-lg); background: white; box-shadow: var(--shadow-sm); }
.metric-card__icon { display: grid; width: 2.5rem; height: 2.5rem; flex: 0 0 auto; place-items: center; border-radius: .75rem; }
.metric-card__icon :deep(svg) { width: 1.12rem; }
.metric-card__icon--mint { background: var(--mint-100); color: var(--mint-700); }.metric-card__icon--violet { background: var(--violet-100); color: var(--violet-600); }.metric-card__icon--amber { background: var(--amber-100); color: var(--amber-600); }.metric-card__icon--ink { background: var(--ink-100); color: var(--ink-800); }
.metric-card p { margin: .05rem 0 .35rem; color: var(--ink-600); font-size: .72rem; font-weight: 650; }
.metric-card strong { display: block; font-size: 1.45rem; line-height: 1; letter-spacing: -.045em; font-variant-numeric: tabular-nums; }
.metric-card span { display: block; margin-top: .42rem; color: var(--ink-500); font-size: .65rem; }
@media (max-width: 540px) { .metric-card { min-height: 102px; padding: .9rem; }.metric-card__icon { width: 2.2rem; height: 2.2rem; }.metric-card strong { font-size: 1.2rem; } }
</style>
