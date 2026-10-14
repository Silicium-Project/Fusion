<template>
  <footer class="public-footer">
    <div class="marketing-container public-footer__top">
      <div class="public-footer__brand"><BrandLogo /><p>{{ t('footer.tagline') }}</p></div>
      <div class="public-footer__links"><strong>{{ t('footer.explore') }}</strong><NuxtLink to="/service">{{ t('nav.product') }}</NuxtLink><NuxtLink to="/download">{{ t('nav.downloadNode') }}</NuxtLink><NuxtLink to="/blockchain">{{ t('nav.blockchain') }}</NuxtLink><NuxtLink to="/about">{{ t('nav.about') }}</NuxtLink><NuxtLink to="/contact">{{ t('nav.ideas') }}</NuxtLink></div>
      <div class="public-footer__links"><strong>{{ t('footer.access') }}</strong><NuxtLink to="/auth?mode=login">{{ t('auth.login') }}</NuxtLink><NuxtLink to="/auth?mode=register">{{ t('nav.signUp') }}</NuxtLink><NuxtLink to="/download">{{ t('footer.installMachine') }}</NuxtLink></div>
      <div class="public-footer__status"><span class="public-footer__status-dot"></span><div><strong>{{ t('footer.devnet') }}</strong><small>{{ t('footer.experimental') }}</small></div></div>
    </div>
    <div class="marketing-container public-footer__bottom"><span>© {{ new Date().getFullYear() }} Silicium Project</span><span>{{ t('footer.motto') }}</span></div>
  </footer>
</template>

<script setup lang="ts">
const { t } = useI18n();
</script>

<style scoped>
.public-footer{margin-top:6rem;border-top:1px solid var(--border);background:rgba(235,240,237,.55)}
.public-footer__top{display:grid;grid-template-columns:1.7fr .65fr .65fr .9fr;gap:2.5rem;padding-block:3.6rem}
.public-footer__brand p{max-width:350px;margin:1rem 0 0;color:var(--ink-700);font-size:.952rem;line-height:1.72}
.public-footer__links{display:grid;align-content:start;gap:.65rem;color:var(--ink-700);font-size:.925rem}.public-footer__links strong{margin-bottom:.3rem;color:var(--ink-900);font-size:.881rem;letter-spacing:.12em;text-transform:uppercase}.public-footer__links a:hover{color:var(--mint-700)}
.public-footer__status{display:flex;align-items:flex-start;gap:.65rem;align-self:start;padding:.85rem;border:1px solid rgba(255,255,255,.8);border-radius:.9rem;background:rgba(255,255,255,.5);box-shadow:inset 0 0 0 1px var(--border)}.public-footer__status-dot{width:.48rem;height:.48rem;margin-top:.22rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .25rem rgba(18,191,174,.12)}.public-footer__status strong,.public-footer__status small{display:block}.public-footer__status strong{font-size:.898rem}.public-footer__status small{margin-top:.2rem;color:var(--ink-500);font-size:.87rem;line-height:1.4}
.public-footer__bottom{display:flex;justify-content:space-between;padding-block:1.2rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.891rem}
@media(max-width:900px){.public-footer__top{grid-template-columns:1.4fr .8fr .8fr}.public-footer__status{grid-column:1/-1;justify-self:start}}
@media(max-width:620px){.public-footer{margin-top:4rem}.public-footer__top{grid-template-columns:1fr 1fr;gap:2.25rem;padding-block:2.75rem}.public-footer__brand{grid-column:1/-1}.public-footer__status{grid-column:1/-1}.public-footer__bottom{align-items:flex-start;flex-direction:column;gap:.45rem}}
</style>
