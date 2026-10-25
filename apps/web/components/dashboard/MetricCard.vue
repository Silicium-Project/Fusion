<template>
  <article class="metric-card">
    <div class="metric-card__icon" :class="`metric-card__icon--${tone}`">
      <UiIcon :name="icon" />
    </div>
    <div>
      <p>{{ label }}</p>
      <strong>{{ value }}</strong
      ><span v-if="detail">{{ detail }}</span>
    </div>
  </article>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string;
    value: string | number;
    detail?: string;
    icon?: string;
    tone?: 'mint' | 'violet' | 'amber' | 'ink';
  }>(),
  { icon: 'activity', tone: 'mint' },
);
</script>

<style scoped>
.metric-card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: flex;
  min-height: 118px;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.15rem;
  border: 1px solid var(--glass-edge);
  border-radius: var(--radius-lg);
  background: var(--glass-card);
  box-shadow: var(--glass-inset), var(--glass-shadow);
  -webkit-backdrop-filter: blur(20px) saturate(1.25);
  backdrop-filter: blur(20px) saturate(1.25);
}
.metric-card::before {
  position: absolute;
  inset: 0;
  background: var(--glass-refraction);
  opacity: 0.22;
  pointer-events: none;
  content: '';
}
.metric-card__glow {
  position: absolute;
  z-index: -1;
  inset: 0;
  opacity: 0;
  background: radial-gradient(
    circle at var(--glow-x) var(--glow-y),
    rgba(255, 255, 255, 0.95),
    rgba(18, 191, 174, 0.08) 28%,
    transparent 60%
  );
  transition: opacity 0.35s;
}
.metric-card:hover {
  box-shadow: var(--glass-inset), var(--shadow-md);
}
.metric-card:hover .metric-card__glow {
  opacity: 1;
}
.metric-card__icon {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 0.75rem;
}
.metric-card__icon :deep(svg) {
  width: 1.12rem;
}
.metric-card__icon--mint {
  background: var(--mint-100);
  color: var(--mint-700);
}
.metric-card__icon--violet {
  background: var(--violet-100);
  color: var(--violet-600);
}
.metric-card__icon--amber {
  background: var(--amber-100);
  color: var(--amber-600);
}
.metric-card__icon--ink {
  background: var(--ink-100);
  color: var(--ink-800);
}
.metric-card p {
  margin: 0.05rem 0 0.35rem;
  color: var(--ink-600);
  font-size: 1rem;
  font-weight: 650;
}
.metric-card strong {
  display: block;
  font-family: var(--font-display);
  font-size: 1.55rem;
  line-height: 1;
  letter-spacing: -0.045em;
  font-variant-numeric: tabular-nums;
}
.metric-card span {
  display: block;
  margin-top: 0.42rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
}
@media (max-width: 540px) {
  .metric-card {
    min-height: 102px;
    padding: 0.9rem;
  }
  .metric-card__icon {
    width: 2.2rem;
    height: 2.2rem;
  }
  .metric-card strong {
    font-size: 1.2rem;
  }
}
@supports not (backdrop-filter: blur(1px)) {
  .metric-card {
    background: var(--surface);
  }
}
</style>
