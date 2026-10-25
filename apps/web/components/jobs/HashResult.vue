<template>
  <div class="hash-result">
    <template v-if="report">
      <div class="hash-result__main">
        <span>{{ report.input_hash ? t('hash.fileHash') : t('hash.listHash') }}</span>
        <code>{{ report.input_hash || report.chunk_list_sha256 }}</code>
        <small>{{
          t('hash.summary', { size: formatBytes(report.size_bytes), count: report.chunk_count })
        }}</small>
      </div>
      <p v-if="!report.input_hash" class="hash-result__note">{{ t('hash.note') }}</p>
      <div v-if="report.chunks.length > 1" class="table-wrap">
        <table class="data-table hash-result__chunks">
          <thead>
            <tr>
              <th>{{ t('hash.chunk') }}</th>
              <th>{{ t('hash.bytes') }}</th>
              <th>SHA-256</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="chunk in visibleChunks" :key="chunk.index">
              <td class="mono">#{{ chunk.index }}</td>
              <td class="mono">{{ chunk.offset }}–{{ chunk.offset + chunk.length }}</td>
              <td class="mono">{{ chunk.sha256 }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <small v-if="report.chunks.length > visibleChunks.length" class="hash-result__more">{{
        t('hash.more', { shown: visibleChunks.length, total: report.chunks.length })
      }}</small>
    </template>
    <div v-else class="hash-result__progress">
      <strong>{{ dashboard.resultReady ? t('hash.readingResult') : t('hash.computing') }}</strong>
      <div
        class="hash-result__bar"
        role="progressbar"
        :aria-valuenow="doneCount"
        :aria-valuemax="total || undefined"
      >
        <i :style="{ width: `${percent}%` }"></i>
      </div>
      <small>{{ t('hash.progress', { done: doneCount, total: total || '—' }) }}</small>
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
const { t, formatBytes } = useI18n();
const config = useRuntimeConfig();
const report = ref<HashReport | null>(null);
const fragments = computed(() => props.dashboard.summary?.fragments || []);
const total = computed(() =>
  Number(props.dashboard.summary?.fragmentCount || fragments.value.length || 0),
);
const doneCount = computed(
  () => fragments.value.filter((item) => fragmentVisualState(item.status) === 'done').length,
);
const percent = computed(() =>
  total.value ? Math.round((doneCount.value * 100) / total.value) : 0,
);
const visibleChunks = computed(() => report.value?.chunks.slice(0, 50) || []);

async function loadReport() {
  if (!props.dashboard.resultReady || report.value || !import.meta.client) return;
  const token = await session.ensureAccessToken();
  if (!token) return;
  const response = await fetch(`${config.public.apiBase}/jobs/${props.dashboard.job.id}/result`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!response.ok) return;
  report.value = parseHashReport(await response.json().catch(() => null));
}

watch(() => props.dashboard.resultReady, loadReport, { immediate: true });
</script>

<style scoped>
.hash-result {
  display: grid;
  gap: 0.9rem;
}
.hash-result__main {
  display: grid;
  gap: 0.45rem;
  padding: 1rem;
  border: 1px solid rgba(18, 191, 174, 0.2);
  border-radius: var(--radius-md);
  background: var(--mint-100);
}
.hash-result__main span {
  color: var(--ink-600);
  font-size: 0.9375rem;
  font-weight: 700;
}
.hash-result__main code {
  overflow-wrap: anywhere;
  color: var(--ink-950);
  font-family: var(--font-mono);
  font-size: 0.9375rem;
}
.hash-result__main small,
.hash-result__more {
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.hash-result__note {
  margin: 0;
  color: var(--ink-600);
  font-size: 0.9375rem;
  line-height: 1.55;
}
.hash-result__chunks {
  min-width: 520px;
}
.hash-result__chunks td:last-child {
  overflow-wrap: anywhere;
}
.hash-result__progress {
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
.hash-result__progress strong {
  font-size: 0.939rem;
}
.hash-result__progress small {
  color: rgba(255, 255, 255, 0.55);
  font-size: 0.9375rem;
}
.hash-result__bar {
  width: min(86%, 420px);
  height: 0.5rem;
  overflow: hidden;
  border-radius: 99px;
  background: #253447;
}
.hash-result__bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #18b5a5, #78d9cd);
  transition: width 0.35s ease;
}
</style>
