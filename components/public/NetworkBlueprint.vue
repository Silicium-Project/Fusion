<template>
  <section class="network-blueprint" :aria-label="t('experience.blueprint.title')">
    <header><span class="marketing-kicker">{{ t('experience.blueprint.label') }}</span><span class="network-blueprint__serial">S / 01</span></header>
    <h2>{{ t('experience.blueprint.title') }}</h2>
    <div class="network-blueprint__stages" role="group" :aria-label="t('experience.blueprint.title')"><button v-for="(label,index) in labels" :key="index" type="button" :aria-pressed="stage === index" @click="stage = index"><span class="network-blueprint__number">0{{ index + 1 }}</span><strong>{{ label }}</strong><UiIcon v-if="index < labels.length - 1" name="arrow"/></button></div>
    <p aria-live="polite">{{ tl('experience.blueprint.descriptions')[stage] }}</p>
  </section>
</template>
<script setup lang="ts">
const { t, tl } = useI18n();
const stage = ref(0);
const labels = computed(() => [t('experience.blueprint.input'), t('experience.blueprint.compute'), t('experience.blueprint.verify'), t('experience.blueprint.output')]);
</script>
<style scoped>
.network-blueprint{min-width:0;padding:1.7rem;border:1px solid var(--glass-edge);border-radius:1.1rem;background:var(--glass-card);box-shadow:var(--glass-inset),var(--shadow-sm)}.network-blueprint header{display:flex;justify-content:space-between;gap:1rem}.network-blueprint__serial{font:400 .9375rem/1.5 var(--font-mono);color:var(--ink-600)}.network-blueprint h2{margin:1rem 0 1.8rem;font-size:1.5rem;font-weight:600;line-height:1.35;letter-spacing:-.03em}.network-blueprint__stages{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.5rem}.network-blueprint__stages button{position:relative;display:grid;gap:.75rem;align-content:start;min-height:6.2rem;padding:1rem;border:1px solid var(--border-strong);border-radius:.5rem;background:rgba(255,255,255,.75);text-align:left;cursor:pointer}.network-blueprint__number{font:400 .9375rem/1.5 var(--font-mono);color:var(--ink-600)}.network-blueprint strong{font-size:1rem;font-weight:550;line-height:1.5;overflow-wrap:anywhere}.network-blueprint__stages svg{position:absolute;top:50%;right:-1.35rem;width:1.1rem;transform:translateY(-50%);color:var(--ink-500)}.network-blueprint button[aria-pressed=true]{border-color:var(--mint-500);background:#f1f7ff;box-shadow:inset 0 2px 0 var(--mint-500)}.network-blueprint>p{min-height:3.5em;margin:1.5rem 0 0;color:var(--ink-600);font-size:1.0625rem;line-height:1.8}
@media(max-width:650px){.network-blueprint{padding:1.25rem}.network-blueprint__stages{grid-template-columns:1fr 1fr;gap:.75rem}.network-blueprint__stages button{min-height:6rem}.network-blueprint__stages svg{display:none}.network-blueprint h2{font-size:1.35rem}}
</style>
