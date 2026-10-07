<template>
  <div class="document-search">
    <div v-if="!dashboard.resultReady" class="document-search__progress">
      <strong>{{ failed ? 'La lecture des documents s’est arrêtée' : 'Lecture de tes documents…' }}</strong>
      <div class="document-search__bar" role="progressbar" :aria-valuenow="progress.done" :aria-valuemax="progress.total || undefined"><i :style="{ width: `${percent}%` }"></i></div>
      <small>{{ progress.total ? `${progress.done} / ${progress.total} passages lus` : 'Préparation des documents' }}</small>
    </div>

    <template v-else>
      <p class="document-search__summary">{{ summaryLine }}</p>
      <UiNotice v-if="skipped.length" tone="warning" :title="skipped.length > 1 ? `${skipped.length} fichiers n’ont pas pu être lus` : 'Un fichier n’a pas pu être lu'">
        <ul class="document-search__skipped"><li v-for="file in skipped" :key="file.name"><strong>{{ file.name }}</strong> : {{ skipReasonLabel(file.reason) }}</li></ul>
      </UiNotice>

      <form class="document-search__form" role="search" @submit.prevent="search()">
        <label class="sr-only" for="document-query">Ta question</label>
        <input id="document-query" v-model="query" class="input" maxlength="1000" placeholder="Pose ta question, par exemple : comment résilier le contrat ?" autocomplete="off">
        <UiButton type="submit" icon="search" :loading="searching" :disabled="!query.trim()">Chercher</UiButton>
      </form>

      <UiNotice v-if="preparing" title="Le moteur de recherche se prépare">La première recherche prend un peu plus de temps. Nouvel essai automatique dans quelques secondes…</UiNotice>
      <UiNotice v-else-if="searchError" tone="danger">{{ searchError }}</UiNotice>
      <p v-else-if="searched && !hits.length" class="document-search__empty">Aucun passage ne correspond. Essaie avec d’autres mots.</p>

      <ol v-if="hits.length" class="document-search__hits" aria-label="Passages trouvés">
        <li v-for="hit in hits" :key="`${hit.jobId}-${hit.passageId}`">
          <div class="document-search__hit-head">
            <span>{{ passageSource(hit) }}</span>
            <UiButton variant="secondary" size="small" icon="external" :loading="opening === hitKey(hit)" @click="open(hit)">Ouvrir</UiButton>
          </div>
          <p><template v-for="(segment, index) in highlightSegments(hit.text, searchedQuery)" :key="index"><mark v-if="segment.match">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template></template></p>
        </li>
      </ol>

      <div class="document-search__footer">
        <UiButton variant="secondary" size="small" icon="plus" :to="addDocumentsLink">Ajouter des documents</UiButton>
        <details class="document-search__advanced">
          <summary>Avancé</summary>
          <p>L’index contient le texte des passages et leurs vecteurs, pour le réutiliser dans tes propres outils (Python, base vectorielle…).</p>
          <UiButton variant="ghost" size="small" icon="download" :loading="downloading" @click="download">Télécharger l’index</UiButton>
        </details>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// Result of a document search ("Recherche dans mes documents"): the reading
// progress while the network works, then a search box over every document
// of the collection, with the passages found and their source.
import type { JobDashboard } from '~/types/api';
import { SearchPreparingError } from '~/composables/useJobs';
import { highlightSegments, passageProgress, passageSource, skipReasonLabel, type DocumentHit } from '~/utils/documents';
import { extractJobError, fragmentVisualState } from '~/utils/jobs';

const props = defineProps<{ dashboard: JobDashboard }>();
const jobs = useJobs();
const query = ref('');
const searchedQuery = ref('');
const hits = ref<DocumentHit[]>([]);
const searching = ref(false);
const searched = ref(false);
const preparing = ref(false);
const searchError = ref('');
const opening = ref('');
const downloading = ref(false);
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let retries = 0;
const MAX_RETRIES = 6;

const fragments = computed(() => props.dashboard.summary?.fragments || []);
const failed = computed(() => ['failed', 'expired', 'cancelled'].includes(props.dashboard.job.status));
const progress = computed(() => passageProgress(fragments.value, (status) => fragmentVisualState(status) === 'done'));
const percent = computed(() => progress.value.total ? Math.round(progress.value.done * 100 / progress.value.total) : 0);
const index = computed(() => props.dashboard.documentIndex);
const skipped = computed(() => index.value?.skipped || []);
const summaryLine = computed(() => {
  const documents = index.value?.documents?.length || 0;
  const passages = Number(index.value?.passageCount || 0);
  if (!documents) return 'Tes documents sont prêts : pose ta question.';
  return `${documents} document${documents > 1 ? 's' : ''} lu${documents > 1 ? 's' : ''}, ${passages} passage${passages > 1 ? 's' : ''}. Pose ta question : la recherche porte aussi sur les documents ajoutés ensuite.`;
});
const addDocumentsLink = computed(() => ({ path: '/jobs/new', query: { workload: 'documents', collection: props.dashboard.job.collectionId || props.dashboard.job.siliciumJobId } }));

const hitKey = (hit: DocumentHit) => `${hit.jobId}-${hit.passageId}`;

async function search(isRetry = false) {
  const text = query.value.trim();
  if (!text) return;
  if (!isRetry) { retries = 0; clearTimeout(retryTimer); }
  searching.value = true;
  searchError.value = '';
  try {
    hits.value = await jobs.searchDocuments(props.dashboard.job.id, text, 10);
    searchedQuery.value = text;
    searched.value = true;
    preparing.value = false;
  } catch (failure) {
    if (failure instanceof SearchPreparingError && retries < MAX_RETRIES) {
      preparing.value = true;
      retries += 1;
      retryTimer = setTimeout(() => search(true), 10_000);
    } else {
      preparing.value = false;
      searchError.value = failure instanceof SearchPreparingError ? failure.message : extractJobError(failure, 'La recherche est momentanément indisponible.');
    }
  } finally {
    searching.value = false;
  }
}

async function open(hit: DocumentHit) {
  opening.value = hitKey(hit);
  searchError.value = '';
  try {
    await jobs.openDocument(hit);
  } catch (failure) {
    searchError.value = failure instanceof Error ? failure.message : 'Le document n’est pas disponible.';
  } finally {
    opening.value = '';
  }
}

async function download() {
  downloading.value = true;
  try { await jobs.downloadResult(props.dashboard.job); } finally { downloading.value = false; }
}

onBeforeUnmount(() => clearTimeout(retryTimer));
</script>

<style scoped>
.document-search{display:grid;gap:.9rem}.document-search__progress{display:grid;min-height:220px;place-items:center;align-content:center;gap:.6rem;padding:2rem;border-radius:var(--radius-md);background:#172231;color:white}.document-search__progress strong{font-size:.82rem}.document-search__progress small{color:rgba(255,255,255,.55);font-size:.64rem}.document-search__bar{width:min(86%,420px);height:.5rem;overflow:hidden;border-radius:99px;background:#253447}.document-search__bar i{display:block;height:100%;background:linear-gradient(90deg,#18b5a5,#78d9cd);transition:width .35s ease}.document-search__summary{margin:0;color:var(--ink-600);font-size:.68rem;line-height:1.55}.document-search__skipped{margin:.35rem 0 0;padding-left:1rem;font-size:.64rem;line-height:1.6}.document-search__form{display:grid;grid-template-columns:1fr auto;gap:.5rem}.document-search__empty{margin:0;color:var(--ink-500);font-size:.68rem}.document-search__hits{display:grid;gap:.6rem;margin:0;padding:0;list-style:none}.document-search__hits li{display:grid;gap:.5rem;padding:.85rem 1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:white}.document-search__hit-head{display:flex;align-items:center;justify-content:space-between;gap:.8rem}.document-search__hit-head span{overflow:hidden;color:var(--ink-900);font-size:.7rem;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.document-search__hits p{margin:0;color:var(--ink-700);font-size:.68rem;line-height:1.65}.document-search__hits mark{padding:0 .1rem;border-radius:.2rem;background:var(--mint-100);color:var(--ink-950);font-weight:700}.document-search__footer{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;padding-top:.6rem;border-top:1px solid var(--border)}.document-search__advanced{max-width:340px;color:var(--ink-500);font-size:.62rem;text-align:right}.document-search__advanced summary{cursor:pointer;font-weight:700}.document-search__advanced p{margin:.5rem 0;line-height:1.5;text-align:left}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media(max-width:620px){.document-search__form{grid-template-columns:1fr}.document-search__footer{flex-direction:column}.document-search__advanced{text-align:left}}
</style>
