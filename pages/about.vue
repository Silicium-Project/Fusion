<template>
  <div class="about-page marketing-page">
    <section class="about-hero marketing-container">
      <div v-reveal class="about-hero__copy"><span class="marketing-kicker">{{ t('about.kicker') }}</span><h1 class="marketing-title">{{ t('about.title') }}<br><em>{{ t('about.titleEm') }}</em></h1><p class="marketing-lede">{{ t('about.lede') }}</p></div>
      <div v-reveal="'right'" class="about-hero__aside marketing-glass"><span class="about-hero__number">01</span><p>{{ t('about.aside') }}</p><span class="about-hero__line"></span><small>{{ t('about.asideTag') }}</small></div>
    </section>

    <section class="manifesto marketing-container marketing-section--tight">
      <div class="manifesto__index"><span>01</span><i></i><small>{{ t('about.manifesto') }}</small></div>
      <div class="manifesto__lead"><span class="marketing-kicker">{{ t('about.buildKicker') }}</span><p>{{ t('about.buildLead') }}</p></div>
      <div class="manifesto__copy"><p v-for="paragraph in tl('about.buildText')" :key="paragraph">{{ paragraph }}</p></div>
    </section>

    <section id="network" class="architecture marketing-container marketing-section">
      <div v-reveal class="marketing-section-heading"><div><span class="marketing-kicker">{{ t('about.rolesKicker') }}</span><h2>{{ t('about.rolesTitle') }}<br>{{ t('about.rolesTitle2') }}</h2></div><p>{{ t('about.rolesText') }}</p></div>
      <div class="architecture__grid marketing-glass"><article v-for="(role,index) in roles" :key="index"><div class="architecture__top"><span class="architecture__index">0{{ index + 1 }}</span><span class="architecture__icon"><UiIcon :name="role.icon" /></span></div><span class="architecture__kicker">{{ role.kicker }}</span><h3>{{ role.title }}</h3><p>{{ role.text }}</p><small>{{ role.output }}</small></article></div>
    </section>

    <section class="values marketing-container marketing-section--tight"><article v-for="(value, index) in tl<{ title: string; text: string }>('about.values')" :key="index"><span class="values__index">0{{ index + 1 }}</span><span class="marketing-kicker">{{ t('about.principle') }}</span><h2>{{ value.title }}</h2><p>{{ value.text }}</p></article></section>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const { t, tl } = useI18n();
const roleIcons = ['layers', 'processor', 'shield', 'database'];
const roles = computed(() => tl<{ kicker: string; title: string; text: string; output: string }>('about.roles').map((role, index) => ({ ...role, icon: roleIcons[index] || 'layers' })));
useSeoMeta({ title: () => t('about.seoTitle'), description: () => t('about.seoDescription') });
</script>

<style scoped>
.about-hero{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(18rem,.48fr);align-items:end;gap:clamp(2.5rem,6vw,6rem);min-height:min(620px,calc(100svh - 5rem));padding-block:clamp(3.5rem,7vw,6rem)}.about-hero__copy{min-width:0}.about-hero__copy .marketing-title{max-width:700px}.about-hero__aside{align-self:end;padding:1.35rem;border-radius:1.35rem;background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(225,248,243,.45));}.about-hero__number{display:block;color:var(--ink-400);font-family:var(--font-mono);font-size:.891rem}.about-hero__aside p{margin:2.2rem 0 3rem;color:var(--ink-800);font-size:1.05rem;line-height:1.55;letter-spacing:-.025em}.about-hero__line{display:block;width:100%;height:1px;background:var(--border)}.about-hero__aside small{display:block;margin-top:.85rem;color:var(--ink-500);font-family:var(--font-mono);font-size:.836rem;letter-spacing:.06em}
.manifesto{display:grid;grid-template-columns:4.5rem minmax(0,1.15fr) minmax(0,.85fr);gap:clamp(1.5rem,4vw,4rem);align-items:start;border-top:1px solid var(--border)}.manifesto__index{display:flex;align-items:flex-start;flex-direction:column;gap:.75rem;color:var(--ink-400);font-family:var(--font-mono);font-size:.864rem}.manifesto__index i{display:block;width:1px;height:4.3rem;background:linear-gradient(var(--mint-500),transparent)}.manifesto__index small{font-size:.83rem;writing-mode:vertical-rl;letter-spacing:.08em}.manifesto__lead p{max-width:670px;margin:1rem 0 0;color:var(--ink-900);font-size:clamp(1.7rem,3.1vw,3rem);font-weight:620;line-height:1.16;letter-spacing:-.05em}.manifesto__copy{padding-top:1.85rem;color:var(--ink-700);font-size:1rem;line-height:1.8}.manifesto__copy p{margin:0 0 1.25rem}
.architecture__grid{display:grid;grid-template-columns:repeat(4,1fr);border-radius:1.8rem;background:linear-gradient(135deg,rgba(255,255,255,.78),rgba(225,248,243,.38))}.architecture__grid article{min-width:0;padding:1.35rem;border-right:1px solid var(--border);transition:transform .3s var(--ease-spring),background .3s ease}.architecture__grid article:last-child{border:0}.architecture__grid article:hover{transform:translateY(-5px);background:rgba(255,255,255,.55)}.architecture__top{display:flex;align-items:center;justify-content:space-between}.architecture__index{color:var(--ink-400);font-family:var(--font-mono);font-size:.857rem}.architecture__icon{display:grid;width:2.65rem;height:2.65rem;place-items:center;border-radius:.8rem;background:var(--mint-100);color:var(--mint-700)}.architecture__grid article:nth-child(3) .architecture__icon,.architecture__grid article:nth-child(4) .architecture__icon{background:var(--violet-100);color:var(--violet-600)}.architecture__icon svg{width:1.05rem}.architecture__kicker{display:block;margin-top:2.3rem;color:var(--mint-700);font-size:.864rem;font-weight:780;letter-spacing:.08em;text-transform:uppercase}.architecture__grid h3{margin:.45rem 0 .55rem;color:var(--ink-900);font-size:1.03rem;letter-spacing:-.035em}.architecture__grid p{min-height:5.3rem;margin:0;color:var(--ink-700);font-size:.939rem;line-height:1.72}.architecture__grid small{display:block;margin-top:1rem;padding-top:.8rem;border-top:1px solid var(--border);color:var(--ink-600);font-size:.87rem;line-height:1.5}
.values{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem}.values article{position:relative;padding:1.35rem 1.4rem 1.5rem;border-top:2px solid var(--ink-900);background:rgba(255,255,255,.25)}.values article:nth-child(2){border-color:var(--mint-500)}.values article:nth-child(3){border-color:var(--violet-500)}.values__index{display:block;margin-bottom:2.8rem;color:var(--ink-400);font-family:var(--font-mono);font-size:.864rem}.values h2{margin:.8rem 0 .55rem;color:var(--ink-900);font-size:1.12rem;letter-spacing:-.04em}.values p{margin:0;color:var(--ink-700);font-size:.959rem;line-height:1.75}
@media(max-width:900px){.about-hero{grid-template-columns:1fr;align-items:start;min-height:auto;gap:3rem}.about-hero__aside{max-width:27rem}.manifesto{grid-template-columns:3.5rem 1fr}.manifesto__copy{grid-column:2;padding-top:0}.architecture__grid{grid-template-columns:1fr 1fr}.architecture__grid article:nth-child(2){border-right:0}.architecture__grid article:nth-child(-n+2){border-bottom:1px solid var(--border)}}
@media(max-width:620px){.about-hero{padding-block:3.5rem 4rem}.about-hero__aside{width:100%}.manifesto{grid-template-columns:2.3rem 1fr;gap:1rem}.manifesto__index small{display:none}.manifesto__lead,.manifesto__copy{grid-column:2}.manifesto__copy{font-size:.986rem}.architecture__grid{grid-template-columns:1fr}.architecture__grid article{border-right:0;border-bottom:1px solid var(--border)}.architecture__grid article:last-child{border-bottom:0}.architecture__grid p{min-height:0}.values{grid-template-columns:1fr}.values__index{margin-bottom:1.6rem}}
</style>
