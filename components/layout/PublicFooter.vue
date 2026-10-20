<template>
  <footer class="public-footer">
    <div class="marketing-container public-footer__top">
      <div class="public-footer__brand"><BrandLogo /><h2>{{ t('experience.footer.title') }}</h2><p>{{ t('experience.footer.description') }}</p></div>
      <div class="public-footer__links"><strong>{{ t('experience.footer.product') }}</strong><NuxtLink to="/service">{{ t('nav.product') }}</NuxtLink><NuxtLink to="/#usages">{{ t('experience.footer.uses') }}</NuxtLink><NuxtLink to="/about">{{ t('nav.about') }}</NuxtLink></div>
      <div class="public-footer__links"><strong>{{ t('experience.footer.participate') }}</strong><NuxtLink to="/jobs/new">{{ t('experience.home.start') }}</NuxtLink><NuxtLink to="/workers">{{ t('observability.worker.nav') }}</NuxtLink><NuxtLink to="/download">{{ t('experience.install') }} Silicium Node</NuxtLink><NuxtLink to="/auth?mode=login">{{ t('nav.signIn') }}</NuxtLink></div>
      <div class="public-footer__links"><strong>{{ t('experience.footer.resources') }}</strong><NuxtLink to="/blockchain">{{ t('nav.blockchain') }}</NuxtLink><NuxtLink to="/service#status">{{ t('experience.footer.network') }}</NuxtLink><NuxtLink to="/contact">{{ t('experience.contact') }}</NuxtLink></div>
    </div>
    <div class="marketing-container public-footer__bottom"><span>© {{ new Date().getFullYear() }} Silicium Project <i>/</i> {{ t('experience.footer.source') }}</span><NuxtLink to="/service#status" class="public-footer__status"><UiStatusBadge :status="status?.network.status || 'unknown'" /><span>{{ t('experience.live.label') }} ↗</span></NuxtLink></div>
  </footer>
</template>
<script setup lang="ts">
const { t } = useI18n();
const { status, refresh } = useSystemStatus();
onMounted(() => { if (!status.value) refresh(); });
</script>
<style scoped>
.public-footer{margin-top:clamp(4rem,7vw,6rem);border-top:1px solid var(--border);background:rgba(245,249,254,.72);color:var(--ink-600)}
.public-footer__top{display:grid;grid-template-columns:1.8fr repeat(3,1fr);gap:2.5rem;padding-block:3.5rem}
.public-footer__brand h2{margin:1.4rem 0 0;color:var(--ink-900);font-size:1.25rem;font-weight:550;letter-spacing:-.03em}.public-footer__brand p{max-width:20rem;margin:.7rem 0 0;font-size:1rem;line-height:1.8}
.public-footer__links{display:grid;align-content:start;gap:.8rem;padding-top:.4rem;font-size:.9375rem;line-height:1.5}.public-footer__links strong{margin-bottom:.4rem;color:var(--ink-900);font-size:.9375rem;font-weight:600}.public-footer__links a:hover{color:var(--mint-700);text-decoration:underline;text-underline-offset:.3rem}
.public-footer__bottom{display:flex;justify-content:space-between;gap:1.5rem;align-items:center;padding-block:1.4rem;border-top:1px solid var(--border);font-size:.9375rem;line-height:1.7}.public-footer__bottom i{margin-inline:.5rem;font-style:normal;color:var(--ink-300)}.public-footer__status{display:flex;align-items:center;gap:.65rem}.public-footer__status>span{white-space:nowrap}
@media(max-width:950px){.public-footer__top{grid-template-columns:1.5fr 1fr 1fr}.public-footer__brand{grid-column:1/-1}.public-footer__brand p{max-width:30rem}.public-footer__bottom{align-items:start;flex-direction:column}}
@media(max-width:520px){.public-footer__top{grid-template-columns:1fr 1fr;gap:2rem;padding-block:2.5rem}.public-footer__links:last-child{grid-column:1/-1}.public-footer__bottom i{display:none}.public-footer__status{flex-wrap:wrap}}
</style>
