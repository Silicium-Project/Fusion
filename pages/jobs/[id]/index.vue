<template>
  <div class="app-page">
    <template v-if="dashboard">
      <header class="job-head">
        <div><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>Tous mes projets</NuxtLink><div class="job-head__title"><span class="job-head__cube"><UiIcon name="cube"/></span><div><div class="cluster"><h1>{{ dashboard.job.title }}</h1><UiStatusBadge :status="dashboard.job.status" /></div><p>{{ dashboard.job.description || 'Calcul distribué sur le réseau Silicium.' }}</p></div></div></div>
        <div class="job-head__actions"><UiButton variant="secondary" icon="refresh" size="small" :loading="loading" @click="load(true)">Rafraîchir</UiButton><UiButton v-if="dashboard.resultReady" icon="download" size="small" @click="download">Télécharger</UiButton><UiButton v-if="cancellable" variant="danger" size="small" @click="confirmOpen = true">Arrêter</UiButton></div>
      </header>
      <UiNotice v-if="jobErrorDetail" tone="danger" title="Le calcul a rencontré une erreur">{{ compactJobError(jobErrorDetail) }}</UiNotice>
      <section class="metric-grid">
        <MetricCard label="Parties" :value="fragmentTotal" :detail="`${fragmentDone} terminées`" icon="layers" tone="mint" />
        <MetricCard label="Machines mobilisées" :value="nodeCount" detail="calcul et vérification" icon="nodes" tone="ink" />
        <MetricCard label="Durée" :value="duration" detail="depuis le démarrage" icon="clock" tone="violet" />
        <MetricCard label="Rendement calcul" :value="computeShare" :detail="performanceDetail" icon="activity" tone="mint" />
        <MetricCard label="Preuves" :value="dashboard.devnet?.signatures?.length || 0" :detail="dashboard.devnet?.enabled ? 'traçabilité active' : 'traçabilité inactive'" icon="shield" :tone="dashboard.devnet?.ok ? 'mint' : 'amber'" />
      </section>
      <div class="job-detail-grid">
        <UiCard id="result" title="Votre résultat" :description="imageJob ? 'Aperçu de l’artefact réassemblé.' : 'Empreintes calculées et vérifiées par le réseau.'" padded><RenderPreview v-if="imageJob" :dashboard="dashboard" :image-url="resultPreview" /><HashResult v-else-if="hashJob" :dashboard="dashboard" /><UiEmptyState v-else title="Résultat téléchargeable" description="Ce type de calcul n’a pas d’aperçu : utilisez « Télécharger »." icon="download" /></UiCard>
        <UiCard title="Étapes du calcul" description="De la réception à la disponibilité du résultat." padded><ExecutionTimeline :dashboard="dashboard" /></UiCard>
      </div>
      <div class="job-detail-grid job-detail-grid--bottom">
        <UiCard title="Fragments" :description="`${fragmentDone} terminés, ${fragmentActive} actifs, ${fragmentFailed} en erreur.`">
          <div v-if="!fragments.length" class="empty-dash"><UiEmptyState title="Aucun fragment publié" description="Les fragments apparaîtront dès que l’orchestrateur aura produit le plan d’exécution." icon="layers" /></div>
          <div v-else class="table-wrap"><table class="data-table fragments-table"><thead><tr><th>Fragment</th><th>Étape</th><th>Nœud</th><th>Statut</th></tr></thead><tbody><tr v-for="(fragment,index) in visibleFragments" :key="fragmentKey(fragment,index)"><td class="mono">#{{ fragmentIndex(fragment,index) }}</td><td>{{ fragmentStateLabel(fragment.status) }}</td><td class="mono">{{ compactIdentifier(fragmentNode(fragment), 10, 5) }}</td><td><UiStatusBadge :status="String(fragment.status || 'unknown')" /></td></tr></tbody></table></div>
          <footer v-if="fragments.length > visibleLimit" class="card-footer">Les {{ visibleLimit }} fragments les plus récents sont affichés sur {{ fragments.length }}.</footer>
        </UiCard>
        <div class="stack">
          <UiCard title="Détails techniques" padded><TechnicalDetails :dashboard="dashboard" /></UiCard>
          <UiCard v-if="dashboard.devnet?.signatures?.length" title="Transactions Devnet" padded><div class="transaction-list"><a v-for="signature in dashboard.devnet.signatures.slice(0,5)" :key="signature" :href="`https://explorer.solana.com/tx/${signature}?cluster=devnet`" target="_blank" rel="noopener noreferrer"><span class="mono">{{ compactIdentifier(signature, 10, 8) }}</span><UiIcon name="external"/></a></div></UiCard>
        </div>
      </div>
    </template>
    <div v-else-if="loading" class="detail-loading"><div class="skeleton"></div><div class="metric-grid"><div v-for="n in 5" :key="n" class="skeleton"></div></div><div class="skeleton large"></div></div>
    <UiCard v-else padded><UiEmptyState title="Projet introuvable" :description="error || 'Ce projet n’existe pas ou n’appartient pas à votre compte.'" icon="alert"><UiButton to="/jobs" variant="secondary" size="small">Retour aux projets</UiButton></UiEmptyState></UiCard>
    <UiModal :open="confirmOpen" title="Arrêter le calcul ?" @close="confirmOpen = false"><p class="modal-copy">Les parties encore en cours recevront une demande d’arrêt. Les résultats déjà vérifiés resteront enregistrés.</p><div class="modal-actions"><UiButton variant="ghost" @click="confirmOpen = false">Continuer le calcul</UiButton><UiButton variant="danger" :loading="cancelling" @click="cancel">Arrêter maintenant</UiButton></div></UiModal>
  </div>
</template>

<script setup lang="ts">
import type { JobDashboard, JobFragment } from '~/types/api';
import { compactIdentifier, formatDuration, formatPerformanceMultiple, formatPerformancePercent } from '~/utils/format';
import { compactJobError, fragmentStateLabel, fragmentVisualState, isHashWorkload, isImageWorkload, isJobCancellable, shouldRefreshJob } from '~/utils/jobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const route = useRoute(); const jobsStore = useJobs(); const session = useSession(); const config = useRuntimeConfig();
const dashboard = ref<JobDashboard | null>(null); const loading = ref(true); const error = ref(''); const confirmOpen = ref(false); const cancelling = ref(false); const resultPreview = ref(''); const previewAttempts = ref(0);
const visibleLimit = 80;
const imageJob = computed(() => isImageWorkload(dashboard.value?.job.workload));
const hashJob = computed(() => isHashWorkload(dashboard.value?.job.workload));
const fragments = computed(() => dashboard.value?.summary?.fragments || []);
const visibleFragments = computed(() => fragments.value.slice(-visibleLimit).reverse());
const jobErrorDetail = computed(() => dashboard.value?.job.errorMessage || dashboard.value?.summary?.failureDetail || dashboard.value?.summary?.traceback || dashboard.value?.summary?.error || '');
const fragmentTotal = computed(() => Number(dashboard.value?.summary?.fragmentCount || dashboard.value?.job.fragmentCount || fragments.value.length || 0));
const fragmentDone = computed(() => fragments.value.filter(item => fragmentVisualState(item.status) === 'done').length);
const fragmentActive = computed(() => fragments.value.filter(item => ['computing','validating'].includes(fragmentVisualState(item.status))).length);
const fragmentFailed = computed(() => fragments.value.filter(item => fragmentVisualState(item.status) === 'failed').length);
const nodeCount = computed(() => new Set(fragments.value.map(fragmentNode).filter(Boolean)).size || Number((dashboard.value?.job.network?.nodes as unknown[])?.length || 0));
const duration = computed(() => dashboard.value ? formatDuration(dashboard.value.job.startedAt, dashboard.value.job.completedAt) : '—');
const performance = computed(() => dashboard.value?.summary?.performance);
const computeShare = computed(() => formatPerformancePercent(performance.value?.compute_to_total_ratio));
const computeNetwork = computed(() => formatPerformanceMultiple(performance.value?.compute_to_network_ratio));
const performanceDetail = computed(() => computeNetwork.value === '—' ? 'mesure réseau indisponible' : `${computeNetwork.value} calcul / réseau`);
const cancellable = computed(() => Boolean(dashboard.value && isJobCancellable(dashboard.value.job.status)));
const shouldPoll = computed(() => Boolean(dashboard.value && (shouldRefreshJob(dashboard.value.job.status, dashboard.value.resultReady) || (imageJob.value && dashboard.value.resultReady && !resultPreview.value && previewAttempts.value < 5))));
function fragmentIndex(fragment: JobFragment, fallback: number) { return fragment.fragment_index ?? fragment.fragmentIndex ?? fallback; }
function fragmentNode(fragment: JobFragment) { return String(fragment.handled_by || fragment.handledBy || 'En attente'); }
function fragmentKey(fragment: JobFragment, fallback: number) { return `${fragmentIndex(fragment,fallback)}-${fragmentNode(fragment)}-${fragment.status}`; }
let loadPromise: Promise<void> | undefined;
function load(force = false, background = false): Promise<void> {
  if (loadPromise) return loadPromise;
  if (!background) loading.value = true;
  error.value = '';
  loadPromise = (async () => {
    try {
      dashboard.value = await jobsStore.getJobDashboard(String(route.params.id), force);
      if (dashboard.value.resultReady && !resultPreview.value) await loadPreview();
    } catch (failure) {
      if (!dashboard.value) {
        const response = failure as { status?: number; statusCode?: number };
        error.value = response.status === 404 || response.statusCode === 404 ? 'Cette tâche est introuvable.' : 'Le détail de cette tâche ne peut pas être chargé.';
      }
    } finally {
      loading.value = false;
      loadPromise = undefined;
    }
  })();
  return loadPromise;
}
async function loadPreview() { if (!dashboard.value?.resultReady || !imageJob.value || !import.meta.client) return; previewAttempts.value += 1; const token = await session.ensureAccessToken(); if (!token) return; const response = await fetch(`${config.public.apiBase}/jobs/${route.params.id}/result`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' }); if (!response.ok || !response.headers.get('content-type')?.startsWith('image/')) return; const next = URL.createObjectURL(await response.blob()); if (resultPreview.value) URL.revokeObjectURL(resultPreview.value); resultPreview.value = next; }
async function download() { if (dashboard.value) await jobsStore.downloadResult(dashboard.value.job); }
async function cancel() { if (!dashboard.value) return; cancelling.value = true; try { await jobsStore.cancelJob(dashboard.value.job.id); confirmOpen.value = false; await load(true); } finally { cancelling.value = false; } }
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { load(); timer = setInterval(() => { if (shouldPoll.value) load(true, true); }, 2_000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); if (resultPreview.value) URL.revokeObjectURL(resultPreview.value); });
useSeoMeta({ title: () => dashboard.value ? `${dashboard.value.job.title} — Silicium` : 'Suivi du projet — Silicium' });
</script>

<style scoped>
.job-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem}.back-link{display:inline-flex;align-items:center;gap:.4rem;margin-bottom:1rem;color:var(--ink-500);font-size:.63rem;font-weight:700}.back-link svg{width:.75rem;transform:rotate(180deg)}.job-head__title{display:flex;align-items:center;gap:.9rem}.job-head__cube{display:grid;width:3.25rem;height:3.25rem;flex:0 0 auto;place-items:center;border-radius:.9rem;background:var(--violet-100);color:var(--violet-600)}.job-head__cube svg{width:1.3rem}.job-head h1{margin:0;font-size:clamp(1.65rem,3vw,2.4rem);letter-spacing:-.05em}.job-head p{margin:.35rem 0 0;color:var(--ink-600);font-size:.7rem}.job-head__actions{display:flex;gap:.45rem}.job-detail-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:1rem}.job-detail-grid--bottom{align-items:start}.fragments-table{min-width:520px}.card-footer{padding:.75rem 1rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.6rem}.transaction-list{display:grid}.transaction-list a{display:flex;align-items:center;justify-content:space-between;padding:.65rem 0;border-bottom:1px solid var(--border);color:var(--ink-700);font-size:.62rem}.transaction-list a:last-child{border:0}.transaction-list svg{width:.8rem;color:var(--mint-700)}.modal-copy{margin:0;color:var(--ink-600);font-size:.8rem;line-height:1.7}.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}.detail-loading{display:grid;gap:1rem}.detail-loading>.skeleton:first-child{height:90px}.detail-loading .metric-grid .skeleton{height:110px}.detail-loading .large{height:420px}
@media(max-width:980px){.job-detail-grid{grid-template-columns:1fr}.job-head{align-items:stretch;flex-direction:column}.job-head__actions{justify-content:flex-end}}@media(max-width:560px){.job-head__title{align-items:flex-start}.job-head__actions{overflow-x:auto;justify-content:flex-start;padding-bottom:.2rem}.job-head__cube{width:2.7rem;height:2.7rem}.job-head__title .cluster{gap:.45rem}.modal-actions{align-items:stretch;flex-direction:column}}
</style>
