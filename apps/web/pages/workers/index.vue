<template>
  <div class="workers-page marketing-page">
    <section class="workers-hero marketing-container">
      <div><span class="marketing-kicker">{{ t('observability.worker.kicker') }}</span><h1 class="marketing-title">{{ t('observability.worker.title') }}<br>{{ t('observability.worker.titleEm') }}</h1><p class="marketing-lede">{{ t('observability.worker.intro') }}</p><div class="marketing-action-row"><UiButton to="/download" size="large" icon="download">{{ t('observability.worker.install') }}</UiButton><UiButton to="/workers/overview" variant="secondary" size="large" icon="arrow">{{ t('observability.worker.open') }}</UiButton></div><p class="workers-hero__platforms">Linux · APT / DNF · Windows</p></div>
      <div class="workers-hero__network"><LiveMetricsPanel/><p>{{ t('observability.worker.networkScope') }}</p></div>
    </section>
    <section class="marketing-container marketing-section workers-steps"><span class="marketing-kicker">{{ t('observability.worker.kicker') }}</span><h2>{{ t('observability.worker.stepsTitle') }}</h2><ol><li v-for="(step,index) in tl<{ title: string; text: string }>('observability.worker.steps')" :key="step.title"><span>0{{ index + 1 }}</span><h3>{{ step.title }}</h3><p>{{ step.text }}</p></li></ol></section>
    <section class="workers-transparency marketing-container marketing-glass">
      <div>
        <span class="marketing-kicker">{{ t('observability.worker.transparency') }}</span>
        <h2>{{ t('observability.telemetry.resources') }}</h2>
        <p>{{ t('observability.worker.transparencyText') }}</p>
        <NuxtLink to="/workers/overview">{{ t('observability.worker.open') }}<UiIcon name="arrow"/></NuxtLink>
      </div>
      <div class="workers-transparency__account">
        <span class="marketing-kicker">{{ t('observability.worker.deviceKicker') }}</span>
        <h3>{{ t('observability.worker.devicePairingTitle') }}</h3>
        <p>{{ t('observability.worker.devicePairingText') }}</p>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
definePageMeta({ layout: 'public' });
const { t, tl } = useI18n();
useSeoMeta({ title: () => `${t('observability.worker.nav')} — Silicium`, description: () => t('observability.worker.intro') });
</script>
<style scoped>
.workers-hero{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:3.5rem;align-items:start;padding-block:clamp(3.5rem,7vw,6rem)}.workers-hero .marketing-title{font-size:clamp(2.7rem,4.2vw,4.25rem)}.workers-hero__platforms{margin:1.5rem 0 0;font-size:1rem;color:var(--ink-600)}.workers-hero__network{min-width:0}.workers-hero__network>p{margin:1rem .2rem 0;color:var(--ink-600);font-size:1rem;line-height:1.7}.workers-steps{border-top:1px solid var(--border)}.workers-steps h2,.workers-transparency h2{margin:1rem 0 0;font-size:clamp(1.9rem,3.2vw,2.8rem);font-weight:600;letter-spacing:-.04em;line-height:1.15}.workers-steps ol{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:3rem;margin:2.5rem 0 0;padding:0;list-style:none}.workers-steps li>span{font:400 1rem/1.5 var(--font-mono);color:var(--mint-700)}.workers-steps h3{margin:1rem 0 .7rem;font-size:1.25rem;font-weight:600}.workers-steps p,.workers-transparency p{margin:.75rem 0 0;color:var(--ink-600);font-size:1.0625rem;line-height:1.8}.workers-transparency{display:grid;grid-template-columns:1.2fr 1fr;gap:4rem;padding:2.5rem;border-radius:1.2rem}.workers-transparency a{display:inline-flex;align-items:center;gap:.75rem;min-height:3rem;margin-top:1.5rem;color:var(--mint-700);font-size:1rem}.workers-transparency a svg{width:1rem}.workers-transparency__account{border-left:1px solid var(--border);padding-left:3rem}.workers-transparency__account h3{margin:.75rem 0 0;font-size:1.35rem;font-weight:600;line-height:1.35}
@media(max-width:1000px){.workers-hero{grid-template-columns:1fr;gap:2.5rem}.workers-hero__network{max-width:44rem}.workers-steps ol{gap:1.5rem}.workers-transparency{gap:2rem}.workers-transparency__account{padding-left:2rem}}
@media(max-width:650px){.workers-hero{padding-block:3rem}.workers-hero .marketing-title{font-size:clamp(2.4rem,8vw,3.6rem)}.workers-steps ol{grid-template-columns:1fr;gap:2.3rem}.workers-steps h3{margin-top:.5rem}.workers-transparency{grid-template-columns:1fr;padding:1.4rem}.workers-transparency__account{border-left:0;border-top:1px solid var(--border);padding:1.7rem 0 0}}
</style>
