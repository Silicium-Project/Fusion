<template>
  <div class="error-page"><PublicHeader/><main><span class="error-page__code">{{ error?.statusCode || 500 }}</span><h1>{{ error?.statusCode === 404 ? 'Cette page n’existe pas.' : 'Quelque chose s’est interrompu.' }}</h1><p>{{ error?.statusCode === 404 ? 'Le lien a peut-être changé ou la ressource n’est plus disponible.' : 'L’incident a été isolé. Revenez à un point connu pour continuer.' }}</p><div class="cluster"><UiButton to="/" icon="arrow">Retour à l’accueil</UiButton><UiButton v-if="error?.statusCode !== 404" variant="secondary" icon="refresh" @click="clearError({ redirect: '/' })">Réessayer</UiButton></div></main></div>
</template>

<script setup lang="ts">
defineProps<{ error: { statusCode?: number; message?: string } }>();
</script>

<style scoped>
.error-page{min-height:100vh;background:var(--paper-warm)}.error-page main{display:grid;min-height:calc(100vh - 4.75rem);place-content:center;justify-items:center;padding:2rem;text-align:center}.error-page__code{color:var(--mint-700);font-size:.7rem;font-weight:850;letter-spacing:.15em}.error-page h1{margin:1rem 0 0;font-size:clamp(2.5rem,6vw,5rem);letter-spacing:-.065em}.error-page p{max-width:520px;margin:1rem 0 2rem;color:var(--ink-600);font-size:.82rem;line-height:1.7}
</style>
