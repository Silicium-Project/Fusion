<template>
  <div class="batch-answers">
    <section v-if="request" class="batch-answers__request" :aria-label="t('batchAI.answers.requestAria')">
      <div class="batch-answers__task"><span class="eyebrow">{{ t(`batchAI.tasks.${request.task}.label`) }}</span><p v-if="request.instruction">« {{ request.instruction }} »</p><p v-else>{{ t('batchAI.answers.itemsArePrompts') }}</p></div>
      <ul v-if="names.length" class="batch-answers__names"><li v-for="name in names" :key="name">{{ name }}</li></ul>
      <small>{{ sourceLine }}</small>
    </section>

    <div v-if="!page?.complete" class="batch-answers__progress">
      <strong>{{ failed ? t('batchAI.answers.stopped') : t('batchAI.answers.running') }}</strong>
      <div class="batch-answers__bar" role="progressbar" :aria-valuenow="available" :aria-valuemax="total || undefined"><i :style="{ width: `${percent}%` }"></i></div>
      <small>{{ t('batchAI.answers.verified', { done: available, total }) }} · {{ t('batchAI.answers.liveHint') }}</small>
    </div>
    <p v-else class="batch-answers__done">{{ t('batchAI.answers.done', { count: total, answered: answered }) }}<template v-if="modelName"> · {{ t('batchAI.answers.model', { name: modelName }) }}</template></p>

    <UiNotice v-if="loadError" tone="danger">{{ loadError }}</UiNotice>
    <div v-if="rows.length" class="table-wrap batch-answers__table">
      <table class="data-table">
        <thead><tr><th class="batch-answers__index">#</th><th>{{ t('batchAI.answers.input') }}</th><th>{{ t('batchAI.answers.output') }}</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="mono batch-answers__index">{{ row.id + 1 }}</td>
            <td><p class="batch-answers__cell" :class="{ 'is-open': opened.has(row.id) }" @click="toggle(row.id)">{{ row.input }}</p></td>
            <td>
              <span v-if="row.output == null" class="batch-answers__none">{{ t('batchAI.answers.none') }}</span>
              <span v-else-if="kind === 'label'" class="batch-answers__label">{{ row.output }}</span>
              <dl v-else-if="typeof row.output === 'object'" class="batch-answers__fields"><template v-for="(value, key) in row.output" :key="key"><dt>{{ key }}</dt><dd>{{ value || '—' }}</dd></template></dl>
              <p v-else class="batch-answers__cell" :class="{ 'is-open': opened.has(-row.id - 1) }" @click="toggle(-row.id - 1)">{{ row.output }}</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <UiEmptyState v-else-if="!loading" :title="t('batchAI.answers.emptyTitle')" :description="t('batchAI.answers.emptyText')" icon="clock" />

    <footer class="batch-answers__footer">
      <div v-if="available > PAGE_SIZE" class="cluster batch-answers__pager">
        <UiButton variant="ghost" size="small" :disabled="offset === 0" @click="go(offset - PAGE_SIZE)">{{ t('batchAI.answers.previous') }}</UiButton>
        <span>{{ t('batchAI.answers.range', { from: offset + 1, to: Math.min(offset + PAGE_SIZE, available), total: available }) }}</span>
        <UiButton variant="ghost" size="small" :disabled="offset + PAGE_SIZE >= available" @click="go(offset + PAGE_SIZE)">{{ t('batchAI.answers.next') }}</UiButton>
      </div>
      <div v-if="page?.complete" class="cluster">
        <UiButton icon="download" size="small" :loading="downloading === 'csv'" @click="download('csv')">{{ t('batchAI.answers.downloadCsv') }}</UiButton>
        <UiButton variant="ghost" size="small" :loading="downloading === 'jsonl'" @click="download('jsonl')">{{ t('batchAI.answers.downloadJsonl') }}</UiButton>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
// Result of a batch AI job ("Traitement par IA"): the request, then the
// answers as the network verifies them (a part's answers appear once
// another machine has checked them), and the table to download at the end.
import type { JobDashboard } from '~/types/api';
import type { BatchAnswer, BatchAnswersPage } from '~/utils/batchAI';
import { extractJobError, fragmentVisualState } from '~/utils/jobs';

const PAGE_SIZE = 50;
const props = defineProps<{ dashboard: JobDashboard }>();
const { t } = useI18n();
const jobs = useJobs();

const page = ref<BatchAnswersPage | null>(null);
const offset = ref(0);
const loading = ref(false);
const loadError = ref('');
const downloading = ref('');
const opened = ref(new Set<number>());

const request = computed(() => props.dashboard.batchAI?.request || null);
const kind = computed(() => request.value?.output.kind || 'text');
const names = computed(() => request.value?.output.labels || request.value?.output.fields || []);
const total = computed(() => page.value?.total || request.value?.itemCount || 0);
const available = computed(() => page.value?.available || 0);
const percent = computed(() => (total.value ? Math.round((available.value / total.value) * 100) : 0));
const answered = computed(() => Number(props.dashboard.batchAI?.result?.answered ?? available.value));
const modelName = computed(() => props.dashboard.batchAI?.result?.model?.id || '');
const rows = computed<BatchAnswer[]>(() => page.value?.items || []);
const failed = computed(() => ['failed', 'cancelled', 'expired'].includes(props.dashboard.job.status) || (props.dashboard.summary?.fragments || []).some((fragment) => fragmentVisualState(fragment.status) === 'failed'));
const sourceLine = computed(() => {
  const source = request.value?.source;
  const count = t('batchAI.itemCount', { count: request.value?.itemCount || 0 });
  if (!source?.name) return count;
  return source.column ? t('batchAI.answers.sourceColumn', { count, name: source.name, column: source.column }) : t('batchAI.answers.source', { count, name: source.name });
});
/** Verified parts so far: the answers are reloaded when it grows. */
const verifiedParts = computed(() => (props.dashboard.summary?.fragments || []).filter((fragment) => fragmentVisualState(fragment.status) === 'done').length);

async function load() {
  loading.value = true;
  try {
    page.value = await jobs.loadAnswers(props.dashboard.job.id, offset.value, PAGE_SIZE);
    loadError.value = '';
  } catch (failure) {
    loadError.value = extractJobError(failure, t('batchAI.answers.loadFailed'));
  } finally {
    loading.value = false;
  }
}

function go(next: number) {
  offset.value = Math.max(0, next);
  void load();
}

function toggle(id: number) {
  const next = new Set(opened.value);
  if (next.has(id)) next.delete(id); else next.add(id);
  opened.value = next;
}

async function download(format: 'csv' | 'jsonl') {
  downloading.value = format;
  try { await jobs.downloadResult(props.dashboard.job, format); } catch (failure) { loadError.value = extractJobError(failure); } finally { downloading.value = ''; }
}

watch([verifiedParts, () => props.dashboard.resultReady], () => { void load(); });
onMounted(load);
</script>

<style scoped>
.batch-answers{display:grid;gap:1rem}
.batch-answers__request{display:grid;gap:.55rem;padding:.9rem 1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.batch-answers__task p{margin:.3rem 0 0;color:var(--ink-900);font-size:.93rem;line-height:1.5;overflow-wrap:anywhere}.batch-answers__request small{color:var(--ink-500);font-size:.85rem}
.batch-answers__names{display:flex;flex-wrap:wrap;gap:.35rem;margin:0;padding:0;list-style:none}.batch-answers__names li,.batch-answers__label{display:inline-block;padding:.2rem .55rem;border-radius:999px;background:var(--mint-100);color:var(--mint-700);font-size:.82rem;font-weight:750}
.batch-answers__progress{display:grid;gap:.45rem}.batch-answers__progress strong{color:var(--ink-900);font-size:.93rem}.batch-answers__progress small{color:var(--ink-500);font-size:.85rem}.batch-answers__bar{height:.5rem;overflow:hidden;border-radius:999px;background:var(--surface-soft)}.batch-answers__bar i{display:block;height:100%;border-radius:inherit;background:var(--mint-500);transition:width .4s}
.batch-answers__done{margin:0;color:var(--ink-700);font-size:.9rem}
.batch-answers__table{max-height:560px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-md)}.batch-answers__table table{min-width:560px}.batch-answers__table td{vertical-align:top}.batch-answers__index{width:3.2rem;color:var(--ink-500)}
.batch-answers__cell{display:-webkit-box;margin:0;overflow:hidden;overflow-wrap:anywhere;-webkit-box-orient:vertical;-webkit-line-clamp:3;line-clamp:3;color:var(--ink-800);font-size:.87rem;line-height:1.5;cursor:pointer;white-space:pre-line}.batch-answers__cell.is-open{display:block}
.batch-answers__none{color:var(--ink-400);font-size:.85rem;font-style:italic}
.batch-answers__fields{display:grid;gap:.15rem;margin:0;font-size:.85rem}.batch-answers__fields dt{color:var(--ink-500);font-size:.78rem;font-weight:700;letter-spacing:.02em}.batch-answers__fields dd{margin:0 0 .3rem;overflow-wrap:break-word;color:var(--ink-900)}
.batch-answers__table th:nth-child(2),.batch-answers__table td:nth-child(2){width:48%}
.batch-answers__footer{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.7rem}.batch-answers__pager span{color:var(--ink-500);font-size:.85rem}
</style>
