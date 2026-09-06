<template>
  <header class="app-header">
    <div class="app-header__mobile-brand"><BrandLogo /></div>
    <div class="app-header__context"><span>{{ section }}</span><strong>{{ title }}</strong></div>
    <div class="app-header__actions">
      <span class="app-header__status"><i></i> Système actif</span>
      <UiButton to="/jobs/new" icon="plus" size="small">Nouvelle tâche</UiButton>
      <NuxtLink to="/profile" class="app-header__avatar" aria-label="Ouvrir mon compte">{{ initials }}</NuxtLink>
    </div>
  </header>
</template>

<script setup lang="ts">
const route = useRoute();
const { initials } = useSession();
const labels: Record<string, [string, string]> = {
  '/dashboard': ['Workspace', 'Vue d’ensemble'], '/jobs': ['Workspace', 'Tâches'], '/jobs/new': ['Tâches', 'Nouvelle tâche'],
  '/network': ['Infrastructure', 'Réseau'], '/nodes': ['Infrastructure', 'Nœuds'], '/profile': ['Compte', 'Paramètres'],
};
const matched = computed(() => route.path.startsWith('/jobs/') && route.path !== '/jobs/new' ? ['Tâches', 'Détail de l’exécution'] : labels[route.path] || ['Silicium', 'Espace de calcul']);
const section = computed(() => matched.value[0]);
const title = computed(() => matched.value[1]);
</script>

<style scoped>
.app-header { position:sticky;top:0;z-index:30;display:flex;height:4.8rem;align-items:center;justify-content:space-between;gap:1rem;padding:0 2rem;border-bottom:1px solid var(--border);background:rgba(244,245,241,.88);backdrop-filter:blur(16px) saturate(1.25) }
.app-header__mobile-brand{display:none}.app-header__context span,.app-header__context strong{display:block}.app-header__context span{color:var(--ink-500);font-size:.61rem;font-weight:750}.app-header__context strong{margin-top:.12rem;font-size:.86rem;letter-spacing:-.02em}.app-header__actions{display:flex;align-items:center;gap:.6rem}.app-header__status{display:inline-flex;align-items:center;gap:.42rem;margin-right:.4rem;color:var(--ink-600);font-size:.66rem;font-weight:650}.app-header__status i{width:.42rem;height:.42rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 4px var(--mint-100)}.app-header__avatar{display:grid;width:2.2rem;height:2.2rem;place-items:center;border:1px solid var(--border);border-radius:.65rem;background:white;color:var(--violet-600);font-size:.64rem;font-weight:850}
@media(max-width:840px){.app-header{height:4.2rem;padding:0 .8rem}.app-header__mobile-brand{display:block}.app-header__context{display:none}.app-header__status,.app-header__actions :deep(.ui-button){display:none}}
</style>
