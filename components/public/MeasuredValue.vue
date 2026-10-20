<template>
  <section class="measured-value marketing-container marketing-section">
    <div class="marketing-section-heading"><div><span class="marketing-kicker">{{ t('observability.value.kicker') }}</span><h2>{{ t('observability.value.title') }}</h2></div><p>{{ t('observability.value.intro') }}</p></div>
    <div class="measured-value__grid"><article v-for="(item,index) in tl<{ title: string; text: string }>('observability.value.benefits')" :key="item.title"><span class="measured-value__number">0{{ index + 1 }}</span><h3>{{ item.title }}</h3><p>{{ item.text }}</p></article></div>
    <NuxtLink to="/service#mesure" class="measured-value__link">{{ t('observability.value.costTitle') }}<UiIcon name="arrow"/></NuxtLink>
  </section>
</template>
<script setup lang="ts">const { t, tl } = useI18n();</script>
<style scoped>
.measured-value{padding-bottom:0;border-top:1px solid var(--border)}.measured-value__grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:2.5rem}.measured-value__number{color:var(--mint-700);font:400 .9375rem/1.5 var(--font-mono)}.measured-value h3{margin:1rem 0 .6rem;font-size:1.25rem;font-weight:600;letter-spacing:-.025em}.measured-value__grid p{max-width:25rem;margin:0;font-size:1.0625rem;line-height:1.8;color:var(--ink-600)}.measured-value__link{display:inline-flex;min-height:3rem;align-items:center;gap:.8rem;margin-top:2rem;color:var(--mint-700);font-size:1rem}.measured-value__link svg{width:1rem}@media(max-width:700px){.measured-value__grid{grid-template-columns:1fr;gap:2rem}.measured-value h3{margin-top:.5rem}.measured-value__grid p{max-width:none}}
</style>
