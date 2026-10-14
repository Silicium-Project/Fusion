<template>
  <div class="error-page">
    <PublicHeader />
    <main class="content-width">
      <section class="error-card surface">
        <div class="error-card__mark" aria-hidden="true"><span></span><span></span><span></span></div>
        <span class="error-page__code">{{ error?.statusCode || 500 }} · {{ error?.statusCode === 404 ? t('errorPage.notFound') : t('errorPage.incident') }}</span>
        <h1>{{ error?.statusCode === 404 ? t('errorPage.notFoundTitle') : t('errorPage.incidentTitle') }}</h1>
        <p>{{ error?.statusCode === 404 ? t('errorPage.notFoundText') : t('errorPage.incidentText') }}</p>
        <div class="cluster">
          <UiButton to="/" icon="arrow">{{ t('auth.backHome') }}</UiButton>
          <UiButton to="/service" variant="secondary">{{ t('errorPage.seeProduct') }}</UiButton>
          <UiButton v-if="error?.statusCode !== 404" variant="secondary" icon="refresh" @click="clearError({ redirect: '/' })">{{ t('common.retry') }}</UiButton>
        </div>
        <nav class="error-card__paths" :aria-label="t('errorPage.shortcuts')">
          <NuxtLink to="/about"><span>{{ t('errorPage.architecture') }}</span><UiIcon name="arrow" /></NuxtLink>
          <NuxtLink to="/contact"><span>{{ t('errorPage.contact') }}</span><UiIcon name="arrow" /></NuxtLink>
          <NuxtLink to="/auth?mode=login"><span>{{ t('errorPage.space') }}</span><UiIcon name="arrow" /></NuxtLink>
        </nav>
      </section>
    </main>
    <PublicFooter />
  </div>
</template>

<script setup lang="ts">
defineProps<{ error: { statusCode?: number; message?: string } }>();
const { t } = useI18n();
</script>

<style scoped>
.error-page{min-height:100vh;background:radial-gradient(circle at 74% 18%,rgba(18,191,174,.1),transparent 24rem),var(--paper-warm)}.error-page main{display:grid;min-height:calc(100svh - 4.75rem);place-content:center;padding-block:clamp(3.5rem,8vw,7rem)}.error-card{position:relative;isolation:isolate;display:grid;justify-items:center;overflow:hidden;padding:clamp(2rem,5vw,4rem);text-align:center}.error-card::before{position:absolute;z-index:-1;top:-10rem;left:50%;width:24rem;height:24rem;transform:translateX(-50%);border-radius:50%;background:radial-gradient(circle,rgba(18,191,174,.14),transparent 68%);content:''}.error-card__mark{display:flex;align-items:center;gap:.35rem;margin-bottom:1.75rem}.error-card__mark span{width:.5rem;height:.5rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 5px rgba(18,191,174,.1)}.error-card__mark span:nth-child(2){background:var(--violet-500);box-shadow:0 0 0 5px rgba(121,109,240,.1)}.error-card__mark span:nth-child(3){background:var(--ink-800);box-shadow:0 0 0 5px rgba(11,21,35,.08)}.error-page__code{color:var(--mint-700);font-size:.891rem;font-weight:850;letter-spacing:.13em;text-transform:uppercase}.error-card h1{max-width:760px;margin:1rem 0 0;font-size:clamp(2.35rem,6vw,4.8rem);line-height:.96;letter-spacing:-.065em}.error-card p{max-width:540px;margin:1rem 0 2rem;color:var(--ink-600);font-size:.939rem;line-height:1.7}.error-card__paths{display:grid;grid-template-columns:repeat(3,1fr);width:min(100%,620px);margin-top:2.25rem;border-top:1px solid var(--border)}.error-card__paths a{display:flex;align-items:center;justify-content:space-between;gap:.65rem;padding:1rem .75rem;border-right:1px solid var(--border);color:var(--ink-600);font-size:.881rem;font-weight:720;text-align:left;transition:color .2s,background .2s}.error-card__paths a:last-child{border:0}.error-card__paths a:hover{background:rgba(225,248,243,.48);color:var(--ink-950)}.error-card__paths svg{width:.75rem;color:var(--mint-700)}
@media(max-width:600px){.error-page main{padding-block:2.5rem}.error-card{padding:2rem 1.1rem}.error-card .cluster{justify-content:center}.error-card .cluster :deep(.ui-button){width:100%}.error-card__paths{grid-template-columns:1fr}.error-card__paths a{border-right:0;border-bottom:1px solid var(--border)}}
</style>
