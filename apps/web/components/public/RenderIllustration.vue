<template>
  <figure class="render-illustration">
    <header>
      <span><UiIcon name="result" />image.png</span
      ><small>{{ t('experience.preview.label') }}</small>
    </header>
    <img
      src="/illustrations/render-study.png"
      :alt="t('experience.preview.alt')"
      width="1448"
      height="1086"
      fetchpriority="high"
    />
    <figcaption>{{ t('experience.preview.caption') }}</figcaption>
  </figure>
</template>
<script setup lang="ts">
const { t } = useI18n();
</script>
<style scoped>
.render-illustration {
  min-width: 0;
  margin: 0;
  padding: 0.8rem;
  border: 1px solid var(--glass-edge);
  border-radius: 1.2rem;
  background: var(--glass-card);
  box-shadow:
    inset 0 1px 0 #fff,
    0 12px 32px rgba(54, 104, 168, 0.065);
}
.render-illustration header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 2.1rem;
  padding: 0 0.3rem 0.6rem;
  color: var(--ink-600);
}
.render-illustration header > span {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.9375rem;
}
.render-illustration header svg {
  width: 0.85rem;
}
.render-illustration header small {
  font-size: 0.9375rem;
}
.render-illustration img {
  width: 100%;
  height: auto;
  aspect-ratio: 4/3;
  object-fit: cover;
  border: 1px solid #dde5ef;
  border-radius: 0.7rem;
}
.render-illustration figcaption {
  padding: 0.8rem 0.3rem 0.2rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
  line-height: 1.6;
}
@media (max-width: 520px) {
  .render-illustration {
    padding: 0.65rem;
    border-radius: 1rem;
  }
  .render-illustration header small {
    font-size: 0.9375rem;
  }
}
</style>
