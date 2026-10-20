<template>
  <figure class="render-illustration">
    <header><span><UiIcon name="result" />image.png</span><small>{{ t('experience.preview.label') }}</small></header>
    <img src="/illustrations/render-study.png" :alt="t('experience.preview.alt')" width="1448" height="1086" fetchpriority="high">
    <figcaption>{{ t('experience.preview.caption') }}</figcaption>
  </figure>
</template>
<script setup lang="ts">
const { t } = useI18n();
</script>
<style scoped>
.render-illustration{min-width:0;margin:0;padding:.8rem;border:1px solid var(--glass-edge);border-radius:1.2rem;background:var(--glass-card);box-shadow:inset 0 1px 0 #fff,0 12px 32px rgba(54,104,168,.065)}
.render-illustration header{display:flex;align-items:center;justify-content:space-between;gap:.75rem;min-height:2.1rem;padding:0 .3rem .6rem;color:var(--ink-600)}.render-illustration header>span{display:flex;align-items:center;gap:.5rem;font-family:var(--font-mono);font-size:.9375rem}.render-illustration header svg{width:.85rem}.render-illustration header small{font-size:.9375rem}.render-illustration img{width:100%;height:auto;aspect-ratio:4/3;object-fit:cover;border:1px solid #dde5ef;border-radius:.7rem}.render-illustration figcaption{padding:.8rem .3rem .2rem;color:var(--ink-500);font-size:.9375rem;line-height:1.6}
@media(max-width:520px){.render-illustration{padding:.65rem;border-radius:1rem}.render-illustration header small{font-size:.9375rem}}
</style>
