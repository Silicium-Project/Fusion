<template>
  <div class="render-preview">
    <img v-if="imageUrl" :src="imageUrl" :alt="t('render.alt')">
    <div v-else class="render-preview__placeholder">
      <div class="render-preview__tiles" :style="tileGridStyle">
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
        <span><i class="is-computing"></i>{{ t('render.computing', { count: computingCount }) }}</span>
        <span><i class="is-validating"></i>{{ t('render.validating', { count: validatingCount }) }}</span>
        <span><i class="is-done"></i>{{ t('render.done', { count: doneCount }) }}</span>
        <span v-if="failedCount"><i class="is-failed"></i>{{ t('render.failed', { count: failedCount }) }}</span>
      </div>
    </div>
    <div class="render-preview__meta"><span><i></i>{{ width }} × {{ height }} px</span><span>Raytracer</span></div>
  </div>
</template>

<script setup lang="ts">
import type { JobDashboard, JobFragment } from '~/types/api';
import { fragmentStateLabel, fragmentVisualState } from '~/utils/jobs';

const props = defineProps<{ dashboard: JobDashboard; imageUrl?: string }>();
const { t } = useI18n();
const fragments = computed(() => props.dashboard.summary?.fragments || []);
const total = computed(() => Number(props.dashboard.summary?.fragmentCount || props.dashboard.job.fragmentCount || fragments.value.length || 0));
const width = computed(() => props.dashboard.summary?.image?.width || '—');
const height = computed(() => props.dashboard.summary?.image?.height || '—');
const tileCount = computed(() => Math.min(256, Math.max(1, total.value || fragments.value.length || 24)));
const fragmentByIndex = computed(() => new Map(fragments.value.map((fragment, fallback) => [fragmentIndex(fragment, fallback), fragment])));
const tiles = computed(() => Array.from({ length: tileCount.value }, (_, index) => {
  const fragment = fragmentByIndex.value.get(index);
  const state = fragmentVisualState(fragment?.status);
  return { index, state, label: fragmentStateLabel(fragment?.status) };
}));
const stateCount = (state: ReturnType<typeof fragmentVisualState>) => tiles.value.filter(tile => tile.state === state).length;
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
  const columns = Math.max(1, Math.ceil(Math.sqrt(tileCount.value * imageWidth / imageHeight)));
  return { '--tile-columns': String(columns) };
});

function fragmentIndex(fragment: JobFragment, fallback: number): number {
  return Number(fragment.fragment_index ?? fragment.fragmentIndex ?? fallback);
}
</script>

<style scoped>
.render-preview{overflow:hidden;border-radius:var(--radius-md);background:#172231;color:white}.render-preview>img{width:100%;min-height:280px;max-height:470px;object-fit:contain;background:#101925}.render-preview__placeholder{display:grid;min-height:310px;place-items:center;align-content:center;padding:2rem}.render-preview__tiles{display:grid;width:min(86%,460px);grid-template-columns:repeat(var(--tile-columns),1fr);gap:3px;transform:perspective(600px) rotateX(48deg) rotateZ(-7deg);filter:drop-shadow(0 18px 16px rgba(0,0,0,.2))}.render-preview__tiles>i{aspect-ratio:1;border:1px solid rgba(255,255,255,.08);border-radius:2px;background:#253447;transition:background .35s ease,box-shadow .35s ease,opacity .35s ease}.render-preview__tiles>i.is-computing{background:linear-gradient(135deg,#227ba7,#42bed3);box-shadow:inset 0 0 0 1px rgba(130,231,247,.28);animation:tile-pulse 1.35s ease-in-out infinite}.render-preview__tiles>i.is-validating{background:linear-gradient(135deg,#6556d9,#a493ef);box-shadow:inset 0 0 0 1px rgba(218,209,255,.3);animation:tile-pulse 1.1s ease-in-out infinite}.render-preview__tiles>i.is-done{background:linear-gradient(135deg,#18b5a5,#78d9cd)}.render-preview__tiles>i.is-failed{background:#c44747}.render-preview__placeholder>strong{margin-top:2.2rem;font-size:.82rem}.render-preview__placeholder>small{margin-top:.35rem;color:rgba(255,255,255,.55);font-size:.64rem}.render-preview__legend{display:flex;flex-wrap:wrap;justify-content:center;gap:.55rem 1rem;margin-top:1rem;color:rgba(255,255,255,.58);font-size:.56rem}.render-preview__legend span{display:inline-flex;align-items:center;gap:.35rem}.render-preview__legend i{width:.45rem;height:.45rem;border-radius:2px;background:#253447}.render-preview__legend .is-computing{background:#42bed3}.render-preview__legend .is-validating{background:#8e7ee9}.render-preview__legend .is-done{background:#49c9ba}.render-preview__legend .is-failed{background:#c44747}.render-preview__meta{display:flex;justify-content:space-between;padding:.7rem .9rem;border-top:1px solid rgba(255,255,255,.08);color:rgba(255,255,255,.48);font-size:.58rem}.render-preview__meta span{display:flex;align-items:center;gap:.4rem}.render-preview__meta i{width:.4rem;height:.4rem;border-radius:50%;background:var(--mint-500)}@keyframes tile-pulse{0%,100%{filter:brightness(.88);opacity:.78}50%{filter:brightness(1.24);opacity:1}}
@media(prefers-reduced-motion:reduce){.render-preview__tiles>i{animation:none!important}}
</style>
