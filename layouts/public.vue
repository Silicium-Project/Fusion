<template>
  <div class="public-layout">
    <a href="#main-content" class="skip-link">{{ t('experience.skip') }}</a>
    <div v-if="isDev" class="development-banner"><div class="marketing-container"><span><i></i>{{ t('experience.devEnvironment') }}<b v-if="version !== 'unknown'">{{ version }}</b></span><NuxtLink to="/download?channel=dev">{{ t('experience.devAccess') }} <span aria-hidden="true">↗</span></NuxtLink></div></div>
    <PublicHeader />
    <main id="main-content" tabindex="-1"><slot /></main>
    <PublicFooter />
  </div>
</template>
<script setup lang="ts">
const { t } = useI18n();
const config = useRuntimeConfig();
const isDev = config.public.releaseChannel !== 'prod';
const version = String(config.public.releaseVersion || 'unknown');
</script>
<style>
.public-layout{min-height:100vh;background:var(--paper-warm)}
.public-layout main{outline:none}
.skip-link{position:fixed;top:.75rem;left:.75rem;z-index:100;transform:translateY(-170%);padding:.8rem 1rem;border-radius:.65rem;background:var(--ink-950);color:white;font-size:.9375rem}.skip-link:focus{transform:translateY(0)}
.development-banner{border-bottom:1px solid #e0e8f3;background:#edf3fc;color:#45617f;font-size:.9375rem;line-height:1.5}.development-banner>.marketing-container{display:flex;justify-content:space-between;align-items:center;gap:1rem;min-height:1.8rem}.development-banner span{display:flex;align-items:center;gap:.5rem}.development-banner i{width:.3rem;height:.3rem;background:#7697c4;border-radius:50%}.development-banner b{font-family:var(--font-mono);font-size:.9375rem;font-weight:400}.development-banner a{display:flex;align-items:center;gap:.5rem}
@media(max-width:520px){.development-banner{font-size:.9375rem}.development-banner a{font-size:0}.development-banner a span{font-size:.9375rem}.development-banner b{display:none}}
</style>
