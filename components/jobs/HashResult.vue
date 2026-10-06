<template>
  <div class="hash-result">
    <template v-if="report">
      <div class="hash-result__main">
        <span>{{ report.input_hash ? 'Empreinte SHA-256 du fichier' : 'Empreinte de la liste des morceaux' }}</span>
        <code>{{ report.input_hash || report.chunk_list_sha256 }}</code>
        <small>{{ formatBytes(report.size_bytes) }} · {{ report.chunk_count }} morceau{{ report.chunk_count > 1 ? 'x' : '' }} haché{{ report.chunk_count > 1 ? 's' : '' }} et vérifié{{ report.chunk_count > 1 ? 's' : '' }} par le réseau</small>
      </div>
      <p v-if="!report.input_hash" class="hash-result__note">Le fichier a été découpé en morceaux calculés sur plusieurs machines : chaque morceau a sa propre empreinte, et la ligne ci-dessus est l’empreinte de leur liste.</p>
      <div v-if="report.chunks.length > 1" class="table-wrap">
        <table class="data-table hash-result__chunks">
          <thead><tr><th>Morceau</th><th>Octets</th><th>SHA-256</th></tr></thead>
          <tbody><tr v-for="chunk in visibleChunks" :key="chunk.index"><td class="mono">#{{ chunk.index }}</td><td class="mono">{{ chunk.offset }}–{{ chunk.offset + chunk.length }}</td><td class="mono">{{ chunk.sha256 }}</td></tr></tbody>
        </table>
      </div>
      <small v-if="report.chunks.length > visibleChunks.length" class="hash-result__more">{{ visibleChunks.length }} morceaux affichés sur {{ report.chunks.length }} ; le fichier téléchargé les contient tous.</small>
    </template>
    <div v-else class="hash-result__progress">
      <strong>{{ dashboard.resultReady ? 'Lecture du résultat…' : 'Calcul des empreintes' }}</strong>
      <div class="hash-result__bar" role="progressbar" :aria-valuenow="doneCount" :aria-valuemax="total || undefined"><i :style="{ width: `${percent}%` }"></i></div>
      <small>{{ doneCount }} / {{ total || '—' }} morceaux terminés</small>
    </div>
  </div>
</template>

<script setup lang="ts">
// Result of a SHA-256 job: the hash report once it is ready, and the chunk
// progress before. The report is the JSON written by the Rust node.
import type { JobDashboard } from '~/types/api';
import { fragmentVisualState, parseHashReport, type HashReport } from '~/utils/jobs';

const props = defineProps<{ dashboard: JobDashboard }>();
const session = useSession();
const config = useRuntimeConfig();
const report = ref<HashReport | null>(null);
const fragments = computed(() => props.dashboard.summary?.fragments || []);
const total = computed(() => Number(props.dashboard.summary?.fragmentCount || fragments.value.length || 0));
const doneCount = computed(() => fragments.value.filter(item => fragmentVisualState(item.status) === 'done').length);
const percent = computed(() => total.value ? Math.round(doneCount.value * 100 / total.value) : 0);
const visibleChunks = computed(() => report.value?.chunks.slice(0, 50) || []);

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
}

async function loadReport() {
  if (!props.dashboard.resultReady || report.value || !import.meta.client) return;
  const token = await session.ensureAccessToken();
  if (!token) return;
  const response = await fetch(`${config.public.apiBase}/jobs/${props.dashboard.job.id}/result`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' });
  if (!response.ok) return;
  report.value = parseHashReport(await response.json().catch(() => null));
}

watch(() => props.dashboard.resultReady, loadReport, { immediate: true });
</script>

<style scoped>
.hash-result{display:grid;gap:.9rem}.hash-result__main{display:grid;gap:.45rem;padding:1rem;border:1px solid rgba(18,191,174,.2);border-radius:var(--radius-md);background:var(--mint-100)}.hash-result__main span{color:var(--ink-600);font-size:.62rem;font-weight:700}.hash-result__main code{overflow-wrap:anywhere;color:var(--ink-950);font-family:var(--font-mono);font-size:.78rem}.hash-result__main small,.hash-result__more{color:var(--ink-500);font-size:.6rem}.hash-result__note{margin:0;color:var(--ink-600);font-size:.64rem;line-height:1.55}.hash-result__chunks{min-width:520px}.hash-result__chunks td:last-child{overflow-wrap:anywhere}.hash-result__progress{display:grid;min-height:220px;place-items:center;align-content:center;gap:.6rem;padding:2rem;border-radius:var(--radius-md);background:#172231;color:white}.hash-result__progress strong{font-size:.82rem}.hash-result__progress small{color:rgba(255,255,255,.55);font-size:.64rem}.hash-result__bar{width:min(86%,420px);height:.5rem;overflow:hidden;border-radius:99px;background:#253447}.hash-result__bar i{display:block;height:100%;background:linear-gradient(90deg,#18b5a5,#78d9cd);transition:width .35s ease}
</style>
