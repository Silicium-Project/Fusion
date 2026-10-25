<template>
  <div class="render-preview">
    <img v-if="imageUrl" :src="imageUrl" :alt="t('render.alt')" />
    <div v-else class="render-preview__placeholder">
      <div
        class="render-preview__tiles"
        :style="tileGridStyle"
        role="img"
        :aria-label="t('render.progress', { done: doneCount, total: total || '—' })"
      >
        <i
          v-for="tile in tiles"
          :key="tile.index"
          :class="`is-${tile.state}`"
          :title="t('render.tile', { index: tile.index + 1, label: tile.label })"
        ></i>
      </div>
      <strong>{{ progressTitle }}</strong>
      <small>{{ t('render.progress', { done: doneCount, total: total || '—' }) }}</small>
      <div class="render-preview__legend">
        <span
          ><i class="is-computing"></i>{{ t('render.computing', { count: computingCount }) }}</span
        >
        <span
          ><i class="is-validating"></i
          >{{ t('render.validating', { count: validatingCount }) }}</span
        >
        <span><i class="is-done"></i>{{ t('render.done', { count: doneCount }) }}</span>
        <span v-if="failedCount"
          ><i class="is-failed"></i>{{ t('render.failed', { count: failedCount }) }}</span
        >
      </div>
    </div>
    <div class="render-preview__meta">
      <span><i></i>{{ width }} × {{ height }} px</span><span>Raytracer</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { JobDashboard, JobFragment } from '~/types/api';
import { fragmentStateLabel, fragmentVisualState } from '~/utils/jobs';

const props = defineProps<{ dashboard: JobDashboard; imageUrl?: string }>();
const { t } = useI18n();
const fragments = computed(() => props.dashboard.summary?.fragments || []);
const total = computed(() =>
  Number(
    props.dashboard.summary?.fragmentCount ||
      props.dashboard.job.fragmentCount ||
      fragments.value.length ||
      0,
  ),
);
const width = computed(() => props.dashboard.summary?.image?.width || '—');
const height = computed(() => props.dashboard.summary?.image?.height || '—');
const tileCount = computed(() =>
  Math.min(256, Math.max(0, total.value || fragments.value.length || 0)),
);
const fragmentByIndex = computed(
  () =>
    new Map(
      fragments.value.map((fragment, fallback) => [fragmentIndex(fragment, fallback), fragment]),
    ),
);
const tiles = computed(() =>
  Array.from({ length: tileCount.value }, (_, index) => {
    const fragment = fragmentByIndex.value.get(index);
    const state = fragmentVisualState(fragment?.status);
    return { index, state, label: fragmentStateLabel(fragment?.status) };
  }),
);
const stateCount = (state: ReturnType<typeof fragmentVisualState>) =>
  fragments.value.filter((fragment) => fragmentVisualState(fragment.status) === state).length;
const computingCount = computed(() => stateCount('computing'));
const validatingCount = computed(() => stateCount('validating'));
const doneCount = computed(() => stateCount('done'));
const failedCount = computed(() => stateCount('failed'));
const progressTitle = computed(() => {
  if (props.dashboard.resultReady) return t('render.preparing');
  if (validatingCount.value) return t('render.validatingTitle');
  if (computingCount.value) return t('render.computingTitle');
  if (doneCount.value) return t('render.assembling');
  return t('render.building');
});
const tileGridStyle = computed(() => {
  const imageWidth = Number(width.value) || 1;
  const imageHeight = Number(height.value) || 1;
  const columns = Math.max(1, Math.ceil(Math.sqrt((tileCount.value * imageWidth) / imageHeight)));
  return { '--tile-columns': String(columns) };
});

function fragmentIndex(fragment: JobFragment, fallback: number): number {
  return Number(fragment.fragment_index ?? fragment.fragmentIndex ?? fallback);
}
</script>

<style scoped>
.render-preview {
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
  color: var(--ink-900);
}
.render-preview > img {
  width: 100%;
  min-height: 260px;
  max-height: 470px;
  object-fit: contain;
  background: #172231;
}
.render-preview__placeholder {
  display: grid;
  min-height: 280px;
  place-items: center;
  align-content: center;
  padding: 2rem;
}
.render-preview__tiles {
  display: grid;
  width: min(86%, 420px);
  grid-template-columns: repeat(var(--tile-columns), 1fr);
  gap: 4px;
}
.render-preview__tiles > i {
  aspect-ratio: 1;
  border: 1px solid var(--border-strong);
  border-radius: 2px;
  background: #e0e8f2;
}
.render-preview__tiles > i.is-computing {
  background: #3485e9;
}
.render-preview__tiles > i.is-validating {
  background: #14294a;
}
.render-preview__tiles > i.is-done {
  background: #479b78;
}
.render-preview__tiles > i.is-failed {
  background: var(--red-600);
}
.render-preview__placeholder > strong {
  margin-top: 1.5rem;
  font-size: 1rem;
  font-weight: 600;
}
.render-preview__placeholder > small {
  margin-top: 0.5rem;
  color: var(--ink-600);
  font-size: 0.9375rem;
}
.render-preview__legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.7rem 1rem;
  margin-top: 1.2rem;
  color: var(--ink-600);
  font-size: 0.9375rem;
}
.render-preview__legend span {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.render-preview__legend i {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 2px;
  background: #e0e8f2;
}
.render-preview__legend .is-computing {
  background: #3485e9;
}
.render-preview__legend .is-validating {
  background: #14294a;
}
.render-preview__legend .is-done {
  background: #479b78;
}
.render-preview__legend .is-failed {
  background: var(--red-600);
}
.render-preview__meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.8rem 1rem;
  border-top: 1px solid var(--border-strong);
  color: var(--ink-600);
  font-size: 0.9375rem;
}
.render-preview__meta span {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.render-preview__meta i {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--mint-700);
}
</style>
