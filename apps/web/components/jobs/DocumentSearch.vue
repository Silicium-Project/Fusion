<template>
  <div class="document-search">
    <div v-if="!dashboard.resultReady" class="document-search__progress">
      <strong>{{ failed ? t('documents.stopped') : t('documents.reading') }}</strong>
      <div
        class="document-search__bar"
        role="progressbar"
        :aria-valuenow="progress.done"
        :aria-valuemax="progress.total || undefined"
      >
        <i :style="{ width: `${percent}%` }"></i>
      </div>
      <small>{{
        progress.total
          ? t('documents.passagesRead', { done: progress.done, total: progress.total })
          : t('documents.preparing')
      }}</small>
    </div>

    <template v-else>
      <p class="document-search__summary">{{ summaryLine }}</p>
      <UiNotice
        v-if="skipped.length"
        tone="warning"
        :title="
          skipped.length > 1
            ? t('documents.skippedMany', { count: skipped.length })
            : t('documents.skippedOne')
        "
      >
        <ul class="document-search__skipped">
          <li v-for="file in skipped" :key="file.name">
            <strong>{{ file.name }}</strong> : {{ skipReasonLabel(file.reason) }}
          </li>
        </ul>
      </UiNotice>

      <section
        v-if="collection.length"
        class="document-search__sources"
        aria-labelledby="document-sources-title"
      >
        <h3 id="document-sources-title">
          {{ t('documents.searchedIn') }}
          <span>{{ t('documents.searchedInCount', { count: collection.length }) }}</span>
        </h3>
        <ul>
          <li v-for="document in visibleDocuments" :key="`${document.jobId}-${document.name}`">
            <button
              type="button"
              :title="t('documents.openDocument', { name: document.name })"
              :disabled="opening === sourceKey(document)"
              @click="openSource(document)"
            >
              <UiIcon name="result" /><span>{{ documentName(document.name) }}</span
              ><small v-if="document.pages">{{
                t('documents.pageShort', { count: document.pages })
              }}</small>
            </button>
          </li>
        </ul>
        <button
          v-if="collection.length > PREVIEWED_DOCUMENTS"
          type="button"
          class="document-search__more"
          :aria-expanded="showAllDocuments"
          @click="showAllDocuments = !showAllDocuments"
        >
          {{
            showAllDocuments
              ? t('documents.showLess')
              : t('documents.showAll', { count: collection.length })
          }}
        </button>
      </section>

      <form class="document-search__form" role="search" @submit.prevent="search()">
        <label class="sr-only" for="document-query">{{ t('documents.question') }}</label>
        <input
          id="document-query"
          v-model="query"
          class="input"
          :maxlength="MAX_QUERY_CHARACTERS"
          :placeholder="t('documents.placeholder')"
          autocomplete="off"
        />
        <UiButton type="submit" icon="search" :loading="searching" :disabled="!query.trim()">{{
          t('documents.search')
        }}</UiButton>
      </form>

      <UiNotice v-if="preparing" :title="t('documents.engineTitle')">{{
        t('documents.engineText')
      }}</UiNotice>
      <UiNotice v-else-if="searchError" tone="danger">{{ searchError }}</UiNotice>
      <p v-else-if="searched && !hits.length" class="document-search__empty">
        {{ t('documents.noMatch') }}
      </p>

      <div v-if="hits.length" class="document-search__results">
        <p class="document-search__count" aria-live="polite">
          {{ t('documents.hitCount', { count: hits.length })
          }}<template v-if="hits.length > VISIBLE_HITS">
            · {{ t('documents.scrollHint') }}</template
          >
        </p>
        <ol
          ref="hitList"
          class="document-search__hits"
          :class="{ 'document-search__hits--scroll': hits.length > VISIBLE_HITS }"
          :style="hitListStyle"
          :aria-label="t('documents.hits')"
          tabindex="0"
        >
          <li v-for="hit in hits" :key="hitKey(hit)" :data-hit="hitKey(hit)">
            <div class="document-search__hit-head">
              <div class="document-search__source">
                <span :title="hit.document">{{ passageSource(hit) }}</span>
                <small v-if="hit.section" :title="hit.section">{{ hit.section }}</small>
              </div>
              <UiButton
                variant="secondary"
                size="small"
                icon="external"
                :loading="opening === hitKey(hit)"
                @click="open(hit)"
                >{{ t('common.open') }}</UiButton
              >
            </div>
            <p :class="{ 'is-clamped': !expanded.has(hitKey(hit)) }">
              <template
                v-for="(segment, index) in highlightSegments(hit.text, searchedQuery)"
                :key="index"
                ><mark v-if="segment.match">{{ segment.text }}</mark
                ><template v-else>{{ segment.text }}</template></template
              >
            </p>
            <button
              v-if="overflowing.has(hitKey(hit)) || expanded.has(hitKey(hit))"
              type="button"
              class="document-search__expand"
              :aria-expanded="expanded.has(hitKey(hit))"
              @click="toggle(hit)"
            >
              {{ expanded.has(hitKey(hit)) ? t('documents.readLess') : t('documents.readMore') }}
            </button>
          </li>
        </ol>
      </div>

      <div class="document-search__footer">
        <UiButton variant="secondary" size="small" icon="plus" :to="addDocumentsLink">{{
          t('documents.addDocuments')
        }}</UiButton>
        <details class="document-search__advanced">
          <summary>{{ t('documents.advanced') }}</summary>
          <p>{{ t('documents.advancedText') }}</p>
          <UiButton
            variant="ghost"
            size="small"
            icon="download"
            :loading="downloading"
            @click="download"
            >{{ t('documents.downloadIndex') }}</UiButton
          >
        </details>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// Result of a document search ("Recherche dans mes documents"): the reading
// progress while the network works, then the documents searched, a search
// box over every document of the collection, and the passages found with
// their source. The first VISIBLE_HITS passages are shown; the list scrolls
// for the next ones instead of lengthening the page.
import type { JobDashboard } from '~/types/api';
import { SearchPreparingError } from '~/composables/useJobs';
import {
  documentName,
  highlightSegments,
  passageProgress,
  passageSource,
  skipReasonLabel,
  uniqueDocuments,
  type CollectionDocument,
  type DocumentHit,
} from '~/utils/documents';
import { extractJobError, fragmentVisualState } from '~/utils/jobs';

/** Passages visible before the list scrolls. */
const VISIBLE_HITS = 5;
/** Passages asked to the API (it allows 50). */
const SEARCHED_HITS = 20;
/** Documents shown before "Show all". */
const PREVIEWED_DOCUMENTS = 8;
/** Same limit as the API (`silicium.MaxSearchQueryRunes`). */
const MAX_QUERY_CHARACTERS = 1000;
const MAX_RETRIES = 6;

const props = defineProps<{ dashboard: JobDashboard }>();
const { t } = useI18n();
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
const showAllDocuments = ref(false);
const expanded = ref(new Set<string>());
/** Passages cut by the four-line clamp, which get a "Read all" button. */
const overflowing = ref(new Set<string>());
const hitList = ref<HTMLOListElement | null>(null);
const listHeight = ref(0);
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let retries = 0;

const fragments = computed(() => props.dashboard.summary?.fragments || []);
const failed = computed(() =>
  ['failed', 'expired', 'cancelled'].includes(props.dashboard.job.status),
);
const progress = computed(() =>
  passageProgress(fragments.value, (status) => fragmentVisualState(status) === 'done'),
);
const percent = computed(() =>
  progress.value.total ? Math.round((progress.value.done * 100) / progress.value.total) : 0,
);
const index = computed(() => props.dashboard.documentIndex);
const skipped = computed(() => index.value?.skipped || []);
/** The documents of the whole collection; this job's own ones with an older API. */
const collection = computed<CollectionDocument[]>(() =>
  uniqueDocuments(
    props.dashboard.collectionDocuments?.length
      ? props.dashboard.collectionDocuments
      : (index.value?.documents || []).map((document) => ({
          ...document,
          jobId: props.dashboard.job.id,
        })),
  ),
);
const visibleDocuments = computed(() =>
  showAllDocuments.value ? collection.value : collection.value.slice(0, PREVIEWED_DOCUMENTS),
);
const summaryLine = computed(() => {
  const documents = index.value?.documents?.length || 0;
  if (!documents) return t('documents.ready');
  return t('documents.summary', {
    count: documents,
    passages: Number(index.value?.passageCount || 0),
  });
});
const addDocumentsLink = computed(() => ({
  path: '/jobs/new',
  query: {
    workload: 'documents',
    collection: props.dashboard.job.collectionId || props.dashboard.job.siliciumJobId,
  },
}));
const hitListStyle = computed(() =>
  hits.value.length > VISIBLE_HITS && listHeight.value
    ? { maxHeight: `${listHeight.value}px` }
    : undefined,
);

const hitKey = (hit: DocumentHit) => `${hit.jobId}-${hit.passageId}`;
const sourceKey = (document: CollectionDocument) => `source-${document.jobId}-${document.name}`;

/**
 * Finds the passages cut by the clamp, then sets the height of the list to
 * that of the first VISIBLE_HITS passages, so that exactly five show.
 */
let measurementVersion = 0;
async function measureList() {
  const version = ++measurementVersion;
  await nextTick();
  if (version !== measurementVersion) return;
  const list = hitList.value;
  if (!list) {
    listHeight.value = 0;
    return;
  }
  const items = list.querySelectorAll<HTMLElement>(':scope > li');
  const cut = new Set<string>();
  items.forEach((item) => {
    const text = item.querySelector<HTMLElement>('p.is-clamped');
    if (text && text.scrollHeight > text.clientHeight + 1 && item.dataset.hit)
      cut.add(item.dataset.hit);
  });
  // An expanded passage is no longer cut but keeps its "Collapse" button.
  const next = new Set([
    ...cut,
    ...[...overflowing.value].filter((key) => expanded.value.has(key)),
  ]);
  if (
    next.size !== overflowing.value.size ||
    [...next].some((key) => !overflowing.value.has(key))
  ) {
    overflowing.value = next;
  }
  // Another measurement may already have changed the Set while its buttons
  // are still waiting for Vue's DOM flush. Always await that flush.
  await nextTick();
  if (version !== measurementVersion || hitList.value !== list) return;
  if (hits.value.length <= VISIBLE_HITS) {
    listHeight.value = 0;
    return;
  }
  const last = items[VISIBLE_HITS - 1];
  if (!last) return;
  // Measured on screen: offsetTop would be relative to a positioned ancestor.
  const bottom =
    last.getBoundingClientRect().bottom - list.getBoundingClientRect().top + list.scrollTop;
  listHeight.value = Math.ceil(bottom + (parseFloat(getComputedStyle(list).paddingBottom) || 0));
}

function toggle(hit: DocumentHit) {
  const next = new Set(expanded.value);
  if (next.has(hitKey(hit))) next.delete(hitKey(hit));
  else next.add(hitKey(hit));
  expanded.value = next;
}

async function search(isRetry = false) {
  const text = query.value.trim();
  if (!text) return;
  if (!isRetry) {
    retries = 0;
    clearTimeout(retryTimer);
  }
  searching.value = true;
  searchError.value = '';
  try {
    hits.value = await jobs.searchDocuments(props.dashboard.job.id, text, SEARCHED_HITS);
    searchedQuery.value = text;
    searched.value = true;
    preparing.value = false;
    expanded.value = new Set();
    overflowing.value = new Set();
    await nextTick();
    if (hitList.value) hitList.value.scrollTop = 0;
    await measureList();
  } catch (failure) {
    if (failure instanceof SearchPreparingError && retries < MAX_RETRIES) {
      preparing.value = true;
      retries += 1;
      retryTimer = setTimeout(() => search(true), 10_000);
    } else {
      preparing.value = false;
      searchError.value =
        failure instanceof SearchPreparingError
          ? failure.message
          : extractJobError(failure, t('errors.searchUnavailable'));
    }
  } finally {
    searching.value = false;
  }
}

async function openDocument(key: string, target: Pick<DocumentHit, 'jobId' | 'document' | 'page'>) {
  opening.value = key;
  searchError.value = '';
  try {
    await jobs.openDocument(target);
  } catch (failure) {
    searchError.value =
      failure instanceof Error ? failure.message : t('errors.documentUnavailable');
  } finally {
    opening.value = '';
  }
}

const open = (hit: DocumentHit) => openDocument(hitKey(hit), hit);
const openSource = (document: CollectionDocument) =>
  openDocument(sourceKey(document), { jobId: document.jobId, document: document.name, page: null });

async function download() {
  downloading.value = true;
  try {
    await jobs.downloadResult(props.dashboard.job);
  } finally {
    downloading.value = false;
  }
}

watch(expanded, () => nextTick(measureList));
const onResize = () => {
  measureList();
};
onMounted(() => window.addEventListener('resize', onResize, { passive: true }));
onBeforeUnmount(() => {
  clearTimeout(retryTimer);
  window.removeEventListener('resize', onResize);
});
</script>

<style scoped>
.document-search {
  display: grid;
  gap: 0.9rem;
}
.document-search__progress {
  display: grid;
  min-height: 220px;
  place-items: center;
  align-content: center;
  gap: 0.6rem;
  padding: 2rem;
  border-radius: var(--radius-md);
  background: #172231;
  color: white;
}
.document-search__progress strong {
  font-size: 0.939rem;
}
.document-search__progress small {
  color: rgba(255, 255, 255, 0.55);
  font-size: 0.9375rem;
}
.document-search__bar {
  width: min(86%, 420px);
  height: 0.5rem;
  overflow: hidden;
  border-radius: 99px;
  background: #253447;
}
.document-search__bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #18b5a5, #78d9cd);
  transition: width 0.35s ease;
}
.document-search__summary {
  margin: 0;
  color: var(--ink-600);
  font-size: 0.9375rem;
  line-height: 1.55;
}
.document-search__skipped {
  margin: 0.35rem 0 0;
  padding-left: 1rem;
  font-size: 0.9375rem;
  line-height: 1.6;
}
.document-search__sources {
  display: grid;
  gap: 0.5rem;
  padding: 0.75rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
}
.document-search__sources h3 {
  margin: 0;
  color: var(--ink-800);
  font-size: 0.9375rem;
  font-weight: 780;
}
.document-search__sources h3 span {
  color: var(--ink-500);
  font-weight: 600;
}
.document-search__sources ul {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.document-search__sources li {
  min-width: 0;
  max-width: 100%;
}
.document-search__sources li button {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 0.4rem;
  padding: 0.38rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: white;
  color: var(--ink-800);
  cursor: pointer;
  font-size: 0.9375rem;
  font-weight: 700;
  transition:
    border-color 0.2s,
    background-color 0.2s;
}
.document-search__sources li button:hover {
  border-color: var(--mint-500);
  background: var(--mint-100);
}
.document-search__sources li button:disabled {
  cursor: progress;
  opacity: 0.6;
}
.document-search__sources li svg {
  flex: none;
  width: 0.75rem;
  color: var(--mint-700);
}
.document-search__sources li span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.document-search__sources li small {
  flex: none;
  color: var(--ink-500);
  font-size: 0.9375rem;
  font-weight: 600;
}
.document-search__more {
  justify-self: start;
  padding: 0;
  border: 0;
  background: none;
  color: var(--mint-700);
  cursor: pointer;
  font-size: 0.9375rem;
  font-weight: 750;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.document-search__form {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.5rem;
}
.document-search__empty {
  margin: 0;
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.document-search__results {
  display: grid;
  gap: 0.45rem;
}
.document-search__count {
  margin: 0;
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.document-search__hits {
  display: grid;
  gap: 0.6rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.document-search__hits--scroll {
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 0.35rem 0.1rem 0;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: var(--border-strong) transparent;
}
.document-search__hits--scroll:focus-visible {
  outline: 2px solid var(--mint-500);
  outline-offset: 2px;
}
.document-search__hits li {
  display: grid;
  gap: 0.5rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: white;
}
.document-search__hit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
}
.document-search__source {
  display: grid;
  gap: 0.1rem;
  min-width: 0;
}
.document-search__source span,
.document-search__source small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.document-search__source span {
  color: var(--ink-900);
  font-size: 0.9375rem;
  font-weight: 750;
}
.document-search__source small {
  color: var(--ink-500);
  font-size: 0.9375rem;
  font-weight: 600;
}
.document-search__hits p {
  margin: 0;
  color: var(--ink-700);
  font-size: 1rem;
  line-height: 1.65;
}
.document-search__hits p.is-clamped {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  line-clamp: 4;
}
.document-search__hits mark {
  padding: 0 0.1rem;
  border-radius: 0.2rem;
  background: var(--mint-100);
  color: var(--ink-950);
  font-weight: 700;
}
.document-search__expand {
  justify-self: start;
  padding: 0;
  border: 0;
  background: none;
  color: var(--mint-700);
  cursor: pointer;
  font-size: 0.9375rem;
  font-weight: 750;
}
.document-search__footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--border);
}
.document-search__advanced {
  max-width: 340px;
  color: var(--ink-500);
  font-size: 0.9375rem;
  text-align: right;
}
.document-search__advanced summary {
  cursor: pointer;
  font-weight: 700;
}
.document-search__advanced p {
  margin: 0.5rem 0;
  line-height: 1.5;
  text-align: left;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
@media (max-width: 620px) {
  .document-search__form {
    grid-template-columns: 1fr;
  }
  .document-search__footer {
    flex-direction: column;
  }
  .document-search__advanced {
    text-align: left;
  }
}
</style>
