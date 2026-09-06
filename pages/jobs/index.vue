<template>
  <div class="app-page">
    <header class="app-page-head"><div><span class="eyebrow">Workspace</span><h1 class="page-title">Tâches</h1><p class="page-intro">Recherchez, filtrez et ouvrez toutes les exécutions rattachées à votre compte.</p></div><UiButton to="/jobs/new" icon="plus">Nouvelle tâche</UiButton></header>
    <UiCard>
      <template #header><div class="jobs-toolbar"><div class="jobs-search"><UiIcon name="search"/><input v-model.trim="search" type="search" placeholder="Rechercher par nom ou identifiant" aria-label="Rechercher une tâche"></div><select v-model="status" class="select" aria-label="Filtrer par statut"><option value="all">Tous les statuts</option><option value="running">En cours</option><option value="queued">En attente</option><option value="completed">Terminées</option><option value="failed">Échouées</option><option value="cancelled">Annulées</option><option value="expired">Expirées</option></select><UiButton variant="secondary" size="small" icon="refresh" :loading="loading" @click="load(true)">Rafraîchir</UiButton></div></template>
      <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
      <JobTable :jobs="filteredJobs" :loading="loading" @cancel="requestCancel" @download="download" />
      <footer v-if="totalPages > 1" class="pagination"><span>Page {{ page }} sur {{ totalPages }} · {{ total }} tâche{{ total > 1 ? 's' : '' }}</span><div><UiButton variant="secondary" size="small" :disabled="page <= 1" @click="page--">Précédente</UiButton><UiButton variant="secondary" size="small" :disabled="page >= totalPages" @click="page++">Suivante</UiButton></div></footer>
    </UiCard>
    <UiModal :open="Boolean(cancelTarget)" title="Arrêter cette tâche ?" @close="cancelTarget = null"><p class="modal-copy">Cette action demande au réseau d’arrêter les fragments encore actifs. Elle ne supprime ni la tâche ni sa trace.</p><div class="modal-actions"><UiButton variant="ghost" @click="cancelTarget = null">Retour</UiButton><UiButton variant="danger" :loading="cancelling" @click="confirmCancel">Confirmer l’arrêt</UiButton></div></UiModal>
  </div>
</template>

<script setup lang="ts">
import type { Job } from '~/types/api';
definePageMeta({ layout: 'app', middleware: 'auth' });
const store = useJobs();
const { jobs, total, loading, error } = store;
const page = ref(1); const pageSize = 20; const status = ref('all'); const search = ref('');
const cancelTarget = ref<Job | null>(null); const cancelling = ref(false);
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const filteredJobs = computed(() => { const query = search.value.toLowerCase(); return query ? jobs.value.filter(job => `${job.title} ${job.siliciumJobId} ${job.workload}`.toLowerCase().includes(query)) : jobs.value; });
async function load(force = false) { await store.loadJobs(page.value, pageSize, status.value, force).catch(() => undefined); }
function requestCancel(job: Job) { cancelTarget.value = job; }
async function confirmCancel() { if (!cancelTarget.value) return; cancelling.value = true; try { await store.cancelJob(cancelTarget.value.id); cancelTarget.value = null; await load(true); } finally { cancelling.value = false; } }
async function download(job: Job) { await store.downloadResult(job).catch(() => undefined); }
watch([page, status], () => { if (status.value !== 'all') page.value = Math.min(page.value, totalPages.value); load(); });
onMounted(() => load());
useSeoMeta({ title: 'Tâches — Silicium' });
</script>

<style scoped>
.jobs-toolbar{display:flex;width:100%;align-items:center;gap:.6rem}.jobs-search{position:relative;min-width:220px;flex:1}.jobs-search svg{position:absolute;top:50%;left:.8rem;width:.9rem;transform:translateY(-50%);color:var(--ink-500)}.jobs-search input{width:100%;height:2.45rem;padding:0 .8rem 0 2.2rem;border:1px solid var(--border);border-radius:.65rem;background:var(--surface-soft);font-size:.7rem}.jobs-toolbar .select{width:auto;min-width:155px;min-height:2.45rem;font-size:.68rem}.pagination{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.2rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.63rem}.pagination>div{display:flex;gap:.4rem}.modal-copy{margin:0;color:var(--ink-600);font-size:.8rem;line-height:1.7}.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}
@media(max-width:650px){.jobs-toolbar{align-items:stretch;flex-wrap:wrap}.jobs-search{flex-basis:100%}.jobs-toolbar .select{flex:1}.pagination{align-items:stretch;flex-direction:column}.pagination>div{justify-content:flex-end}}
</style>
