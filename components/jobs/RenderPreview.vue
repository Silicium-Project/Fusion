<template>
  <div class="render-preview">
    <img v-if="imageUrl" :src="imageUrl" alt="Aperçu du résultat calculé">
    <div v-else class="render-preview__placeholder"><div class="render-preview__tiles"><i v-for="n in tileCount" :key="n" :class="tileTone(n)"></i></div><strong>{{ resultReady ? 'Préparation de l’aperçu' : 'Résultat en construction' }}</strong><small>{{ completed }} / {{ total || '—' }} fragments disponibles</small></div>
    <div class="render-preview__meta"><span><i></i>{{ width }} × {{ height }} px</span><span>Raytracer</span></div>
  </div>
</template>

<script setup lang="ts">
import type { JobDashboard } from '~/types/api';
const props = defineProps<{ dashboard: JobDashboard; imageUrl?: string }>();
const fragments = computed(() => props.dashboard.summary?.fragments || []);
const total = computed(() => Number(props.dashboard.summary?.fragmentCount || props.dashboard.job.fragmentCount || fragments.value.length || 0));
const completed = computed(() => fragments.value.filter(item => ['completed','verified'].includes(String(item.status))).length);
const tileCount = computed(() => Math.min(48, Math.max(12, total.value || 24)));
const resultReady = computed(() => props.dashboard.resultReady);
const width = computed(() => props.dashboard.summary?.image?.width || '—');
const height = computed(() => props.dashboard.summary?.image?.height || '—');
function tileTone(index: number) { if (!fragments.value.length) return ''; const fragment = fragments.value[(index - 1) % fragments.value.length]; return ['completed','verified'].includes(String(fragment?.status)) ? 'done' : String(fragment?.status) === 'failed' ? 'failed' : ''; }
</script>

<style scoped>
.render-preview{overflow:hidden;border-radius:var(--radius-md);background:#172231;color:white}.render-preview>img{width:100%;min-height:280px;max-height:470px;object-fit:contain;background:#101925}.render-preview__placeholder{display:grid;min-height:310px;place-items:center;align-content:center;padding:2rem}.render-preview__tiles{display:grid;width:min(80%,360px);grid-template-columns:repeat(8,1fr);gap:3px;transform:perspective(500px) rotateX(55deg) rotateZ(-10deg);filter:drop-shadow(0 18px 16px rgba(0,0,0,.2))}.render-preview__tiles i{aspect-ratio:1;border:1px solid rgba(255,255,255,.08);border-radius:2px;background:#253447}.render-preview__tiles i.done{background:linear-gradient(135deg,#18b5a5,#78d9cd)}.render-preview__tiles i.done:nth-child(5n){background:linear-gradient(135deg,#7568e8,#a69cf2)}.render-preview__tiles i.failed{background:#c44747}.render-preview__placeholder strong{margin-top:2.2rem;font-size:.82rem}.render-preview__placeholder small{margin-top:.35rem;color:rgba(255,255,255,.45);font-size:.64rem}.render-preview__meta{display:flex;justify-content:space-between;padding:.7rem .9rem;border-top:1px solid rgba(255,255,255,.08);color:rgba(255,255,255,.48);font-size:.58rem}.render-preview__meta span{display:flex;align-items:center;gap:.4rem}.render-preview__meta i{width:.4rem;height:.4rem;border-radius:50%;background:var(--mint-500)}
</style>
