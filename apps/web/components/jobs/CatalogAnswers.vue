<template>
  <div class="catalog-answers">
    <section v-if="request" class="catalog-answers__request" :aria-label="t('catalogAI.answers.requestAria')">
      <span class="eyebrow">{{ taskLabel }}</span>
      <p><a :href="`https://huggingface.co/${request.model.repository}/tree/${request.model.revision}`" target="_blank" rel="noopener noreferrer">{{ request.model.repository }}</a> · {{ request.model.licence }}</p>
      <small>{{ t('catalogAI.itemCount', { count: request.itemCount }) }}<template v-if="request.source?.name"> · {{ request.source.name }}</template></small>
    </section>

    <div v-if="!page?.complete" class="catalog-answers__progress">
      <strong>{{ failed ? t('catalogAI.answers.stopped') : t('catalogAI.answers.running') }}</strong>
      <small>{{ t('catalogAI.answers.runningHint') }}</small>
    </div>
    <p v-else class="catalog-answers__done">{{ t('catalogAI.answers.done', { count: page.available }) }}</p>

    <UiNotice v-if="loadError" tone="danger">{{ loadError }}</UiNotice>
    <div v-if="rows.length" class="table-wrap catalog-answers__table">
      <table class="data-table">
        <thead><tr><th class="catalog-answers__index">#</th><th>{{ t('catalogAI.answers.input') }}</th><th>{{ t('catalogAI.answers.output') }}</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="mono catalog-answers__index">{{ row.id + 1 }}</td>
            <td><span class="catalog-answers__input">{{ request?.previews?.[row.id] ?? '' }}</span></td>
            <td><p class="catalog-answers__cell">{{ outputSummary(row.output) }}</p></td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer v-if="page?.complete" class="catalog-answers__footer">
      <div v-if="page.available > PAGE_SIZE" class="cluster">
        <UiButton variant="ghost" size="small" :disabled="offset === 0" @click="go(offset - PAGE_SIZE)">{{ t('catalogAI.answers.previous') }}</UiButton>
        <span>{{ t('catalogAI.answers.range', { from: offset + 1, to: Math.min(offset + PAGE_SIZE, page.available), total: page.available }) }}</span>
        <UiButton variant="ghost" size="small" :disabled="offset + PAGE_SIZE >= page.available" @click="go(offset + PAGE_SIZE)">{{ t('catalogAI.answers.next') }}</UiButton>
      </div>
      <UiButton icon="download" size="small" :loading="downloading" @click="download">{{ t('catalogAI.answers.download') }}</UiButton>
    </footer>
  </div>
</template>

<script setup lang="ts">
// Result of a catalogue job: the task and the model, then the outputs of
// every item once the job is done (summarised for the table; the JSON Lines
// download has them whole, in the Hub's task schemas).
import type { JobDashboard } from '~/types/api';
import { hfTaskOf, outputSummary, type CatalogAnswer, type CatalogAnswersPage } from '~/utils/hfCatalog';
import { extractJobError } from '~/utils/jobs';

const PAGE_SIZE = 50;
const props = defineProps<{ dashboard: JobDashboard }>();
const { t } = useI18n();
const jobs = useJobs();

const page = ref<CatalogAnswersPage | null>(null);
const offset = ref(0);
const loadError = ref('');
const downloading = ref(false);

const request = computed(() => props.dashboard.hf?.request || null);
const taskLabel = computed(() => request.value?.task || hfTaskOf(props.dashboard.job.workload));
const rows = computed<CatalogAnswer[]>(() => page.value?.items || []);
const failed = computed(() => ['failed', 'cancelled', 'expired'].includes(props.dashboard.job.status));

async function load() {
  try {
    page.value = (await jobs.loadAnswers(props.dashboard.job.id, offset.value, PAGE_SIZE)) as unknown as CatalogAnswersPage;
    loadError.value = '';
  } catch (failure) {
    loadError.value = extractJobError(failure, t('catalogAI.answers.loadFailed'));
  }
}

function go(next: number) {
  offset.value = Math.max(0, next);
  void load();
}

async function download() {
  downloading.value = true;
  try { await jobs.downloadResult(props.dashboard.job); } catch (failure) { loadError.value = extractJobError(failure); } finally { downloading.value = false; }
}

watch(() => props.dashboard.resultReady, () => { void load(); });
onMounted(load);
</script>

<style scoped>
.catalog-answers{display:grid;gap:1rem}
.catalog-answers__request{display:grid;gap:.35rem;padding:.9rem 1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.catalog-answers__request p{margin:0;color:var(--ink-900);font-size:.92rem;overflow-wrap:anywhere}.catalog-answers__request a{color:var(--mint-700);font-family:var(--font-mono);font-weight:700}.catalog-answers__request small{color:var(--ink-500);font-size:.85rem}
.catalog-answers__progress{display:grid;gap:.3rem}.catalog-answers__progress strong{font-size:.93rem}.catalog-answers__progress small,.catalog-answers__done{margin:0;color:var(--ink-600);font-size:.88rem}
.catalog-answers__table{max-height:560px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-md)}.catalog-answers__table table{min-width:520px}.catalog-answers__table td{vertical-align:top}.catalog-answers__index{width:3.2rem;color:var(--ink-500)}
.catalog-answers__input{color:var(--ink-600);font-size:.85rem;overflow-wrap:anywhere}.catalog-answers__cell{margin:0;color:var(--ink-900);font-size:.87rem;line-height:1.5;overflow-wrap:anywhere;white-space:pre-line}
.catalog-answers__footer{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.7rem}.catalog-answers__footer span{color:var(--ink-500);font-size:.85rem}
</style>
