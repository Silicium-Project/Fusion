<template>
  <div class="home-page marketing-page">
    <section class="home-hero marketing-container">
      <div class="home-hero__copy">
        <span class="marketing-kicker">{{ t('experience.home.kicker') }}</span>
        <h1>{{ t('observability.home.title') }}<br>{{ t('observability.home.titleEm') }}</h1>
        <p class="marketing-lede">{{ t('observability.home.intro') }}</p>
        <div class="marketing-action-row">
          <UiButton to="/jobs/new" size="large" icon="arrow">{{ t('experience.home.start') }}</UiButton>
          <UiButton to="/workers" variant="secondary" size="large">{{ t('observability.worker.nav') }}</UiButton>
        </div>
        <NuxtLink to="#usages" class="home-hero__contribute">{{ t('experience.home.explore') }}<UiIcon name="arrow" /></NuxtLink>
      </div>
      <LiveMetricsPanel />
    </section>
    <MeasuredValue />
    <section id="usages" class="home-uses marketing-container marketing-section">
      <div class="marketing-section-heading"><div><span class="marketing-kicker">{{ t('experience.home.usesKicker') }}</span><h2>{{ t('experience.home.usesTitle') }}</h2></div></div>
      <div class="home-uses__grid">
        <NuxtLink v-for="item in uses" :key="item.workload" :to="{ path: '/jobs/new', query: { workload: item.workload } }" class="use-row">
          <span class="use-row__icon"><UiIcon :name="item.icon" /></span>
          <div><h3>{{ item.tag }}</h3><p>{{ item.text }}</p><span class="use-row__action">{{ t('experience.home.useAction') }}<UiIcon name="arrow" /></span></div>
        </NuxtLink>
      </div>
    </section>
    <section class="home-process marketing-container">
      <span class="marketing-kicker">{{ t('experience.home.processKicker') }}</span>
      <h2>{{ t('experience.home.processTitle') }}</h2>
      <ol><li v-for="(step, index) in tl<{ title: string; text: string }>('experience.home.steps')" :key="step.title"><span class="home-process__number">{{ index + 1 }}</span><h3>{{ step.title }}</h3><p>{{ step.text }}</p></li></ol>
      <div class="home-process__links"><NuxtLink to="/service">{{ t('experience.home.processAction') }}<UiIcon name="arrow" /></NuxtLink><NuxtLink to="/blockchain">{{ t('experience.home.trustAction') }}<UiIcon name="arrow" /></NuxtLink></div>
    </section>
    <section class="home-contribute marketing-container marketing-glass">
      <span class="home-contribute__icon" aria-hidden="true"><UiIcon name="processor" /></span>
      <div><h2>{{ t('observability.worker.title') }} {{ t('observability.worker.titleEm') }}</h2><p>{{ t('observability.worker.intro') }}</p></div>
      <div class="home-contribute__action"><UiButton to="/workers" icon="arrow">{{ t('observability.home.workerLink') }}</UiButton><small>APT · DNF · Windows</small></div>
    </section>
    <section class="home-faq marketing-container">
      <span class="marketing-kicker">{{ t('experience.home.faqTitle') }}</span>
      <div><details v-for="item in tl<{ question: string; answer: string }>('experience.home.faq')" :key="item.question"><summary>{{ item.question }}<UiIcon name="chevron" /></summary><p>{{ item.answer }}</p></details></div>
    </section>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const { t, tl } = useI18n();
const definitions = [
  { workload: 'raytracer', icon: 'cube' },
  { workload: 'documents', icon: 'search' },
  { workload: 'ai', icon: 'sparkle' },
  { workload: 'calcul/integrity/sha256', icon: 'shield' },
];
const uses = computed(() => tl<{ title: string; tag: string; text: string }>('experience.home.uses').map((item, index) => ({ ...item, ...definitions[index]! })));
useSeoMeta({ title: () => t('home.seoTitle'), description: () => t('observability.home.intro') });
</script>

<style scoped>
.home-hero{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,1fr);align-items:start;gap:clamp(2rem,5vw,4.5rem);padding-block:clamp(3.5rem,7vw,6rem)}.home-hero__copy{min-width:0}.home-hero h1{margin:1.15rem 0 0;color:var(--ink-950);font-size:clamp(2.65rem,4.3vw,4.35rem);font-weight:650;line-height:1.08;letter-spacing:-.055em;text-wrap:balance}.home-hero .marketing-lede{max-width:31rem}.home-hero__contribute{display:inline-flex;align-items:center;gap:.55rem;margin-top:1.4rem;color:var(--mint-700);font-size:.9375rem;text-underline-offset:.3rem}.home-hero__contribute:hover{text-decoration:underline}.home-hero__contribute svg{width:1rem}
.home-uses__grid{display:grid;grid-template-columns:1fr 1fr;column-gap:clamp(2rem,6vw,5rem);row-gap:2.7rem}.use-row{display:grid;grid-template-columns:3.2rem minmax(0,1fr);align-content:start;gap:1.15rem;border-radius:.75rem}.use-row__icon{display:grid;width:3.2rem;height:3.2rem;place-items:center;border:1px solid #e4edf8;border-radius:50%;background:#eff5fc;color:var(--ink-800);transition:background .2s}.use-row__icon svg{width:1.3rem;height:1.3rem}.use-row h3{margin:.2rem 0 .55rem;font-size:1.08rem;font-weight:600;letter-spacing:-.025em}.use-row p{max-width:27rem;margin:0;color:var(--ink-600);font-size:1.0625rem;line-height:1.75}.use-row__action{display:inline-flex;align-items:center;gap:.6rem;margin-top:.85rem;color:var(--mint-700);font-size:.9375rem}.use-row__action svg{width:.9rem}.use-row:hover .use-row__icon{background:var(--mint-100)}.use-row:hover .use-row__action{text-decoration:underline;text-underline-offset:.25rem}
.home-process{padding-block:.5rem var(--section-space)}.home-process h2{margin:.85rem 0 2.4rem;font-size:clamp(2rem,3.2vw,3rem);font-weight:600;letter-spacing:-.045em;line-height:1.15}.home-process ol{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:2rem;margin:0;padding:0;list-style:none}.home-process li{position:relative;min-width:0}.home-process li:not(:last-child)::after{position:absolute;top:1rem;left:3rem;right:0;height:1px;background:#d8e6f6;content:''}.home-process__number{display:grid;width:2rem;height:2rem;place-items:center;border:1px solid #d2e4fa;border-radius:50%;background:linear-gradient(180deg,#f6faff,#eaf3ff);color:var(--mint-700);font-size:.9375rem;box-shadow:inset 0 1px 0 #fff}.home-process h3{margin:1rem 0 .55rem;font-size:1rem;font-weight:550}.home-process li p{margin:0;color:var(--ink-600);font-size:1.0625rem;line-height:1.75}.home-process__links{display:flex;flex-wrap:wrap;gap:1.5rem;margin-top:1.75rem}.home-process__links a{display:inline-flex;align-items:center;gap:.5rem;color:var(--mint-700);font-size:.9375rem}.home-process__links a:hover{text-decoration:underline;text-underline-offset:.3rem}.home-process__links svg{width:.9rem}
.home-contribute{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:1.6rem;padding:2rem;border-radius:1.2rem;background:linear-gradient(120deg,#f5faffd9,#ffffffc9)}.home-contribute__icon{display:grid;width:3.3rem;height:3.3rem;place-items:center;border:1px solid #fff;border-radius:50%;background:var(--mint-100);color:var(--mint-800)}.home-contribute__icon svg{width:1.5rem}.home-contribute h2{max-width:38rem;margin:0;font-size:clamp(1.25rem,2vw,1.65rem);font-weight:600;letter-spacing:-.035em;line-height:1.3}.home-contribute p{max-width:36rem;margin:.65rem 0 0;color:var(--ink-600);font-size:1.0625rem;line-height:1.75}.home-contribute__action{display:grid;justify-items:center;gap:.65rem}.home-contribute__action small{color:var(--ink-500);font-size:.9375rem}
.home-faq{padding-top:var(--section-space)}.home-faq>div{margin-top:1.2rem}.home-faq details{border-bottom:1px solid var(--border)}.home-faq details:first-child{border-top:1px solid var(--border)}.home-faq summary{display:flex;min-height:3.8rem;align-items:center;justify-content:space-between;gap:1rem;padding-block:1rem;list-style:none;cursor:pointer;font-size:.95rem;font-weight:500}.home-faq summary::-webkit-details-marker{display:none}.home-faq summary svg{width:1rem;flex:none;color:var(--ink-500);transform:rotate(90deg)}.home-faq details[open] summary svg{transform:rotate(-90deg)}.home-faq details p{max-width:55rem;margin:0;padding:0 2rem 1.4rem 0;color:var(--ink-600);font-size:.95rem;line-height:1.8}
@media(max-width:980px){.home-hero{gap:2rem}.home-hero h1{font-size:clamp(2.5rem,4.7vw,4rem)}.home-process ol{grid-template-columns:1fr 1fr;row-gap:2rem}.home-process li:nth-child(2)::after{display:none}.home-contribute{grid-template-columns:auto 1fr}.home-contribute__action{grid-column:2;justify-items:start}}
@media(max-width:760px){.home-hero{grid-template-columns:1fr;gap:2.5rem;padding-block:3.3rem 3rem}.home-hero h1{max-width:36rem;font-size:clamp(2.5rem,8.5vw,3.7rem)}.home-hero :deep(.render-illustration){width:min(100%,36rem)}.home-uses__grid{column-gap:2rem}.use-row{grid-template-columns:2.7rem 1fr;gap:.85rem}.use-row__icon{width:2.7rem;height:2.7rem}}
@media(max-width:540px){.home-uses__grid{grid-template-columns:1fr;gap:0}.use-row{padding:1.5rem 0;border-bottom:1px solid var(--border)}.use-row:first-child{padding-top:0}.use-row h3{font-size:1.02rem}.home-process ol{grid-template-columns:1fr;gap:0}.home-process li{display:grid;grid-template-columns:2rem 1fr;column-gap:1rem;padding-bottom:1.6rem}.home-process__number{grid-row:1/3;z-index:1}.home-process h3{margin:.2rem 0 .45rem}.home-process li p{grid-column:2}.home-process li:not(:last-child)::after{display:block;top:2rem;left:1rem;bottom:0;right:auto;width:1px;height:auto}.home-process__links{gap:1rem}.home-contribute{grid-template-columns:1fr;gap:1rem;padding:1.4rem}.home-contribute__icon{width:2.8rem;height:2.8rem}.home-contribute__action{grid-column:1;justify-items:stretch}.home-contribute__action small{text-align:center}.home-contribute h2{font-size:1.4rem}}
</style>
