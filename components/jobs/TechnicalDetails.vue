<template>
  <dl class="technical-details">
    <div v-for="item in items" :key="item.label"><dt>{{ item.label }}</dt><dd :class="{ mono: item.mono }" :title="item.value">{{ item.value }}</dd></div>
  </dl>
</template>

<script setup lang="ts">
import type { JobDashboard } from '~/types/api';
import { compactIdentifier, formatMilliseconds, formatPerformanceMultiple, formatPerformancePercent } from '~/utils/format';
const props = defineProps<{ dashboard: JobDashboard }>();
const items = computed(() => {
  const performance = props.dashboard.summary?.performance;
  return [
    { label: 'Identifiant réseau', value: props.dashboard.job.siliciumJobId || '—', mono: true },
    { label: 'Charge', value: props.dashboard.job.workload || '—', mono: false },
    { label: 'Priorité', value: props.dashboard.job.priority || '—', mono: false },
    { label: 'Temps de calcul', value: formatMilliseconds(performance?.compute_ms), mono: true },
    { label: 'Temps réseau / coordination', value: formatMilliseconds(performance?.network_ms), mono: true },
    { label: 'Calcul / temps total', value: formatPerformancePercent(performance?.compute_to_total_ratio), mono: true },
    { label: 'Calcul / réseau', value: formatPerformanceMultiple(performance?.compute_to_network_ratio), mono: true },
    { label: 'Unités facturables', value: String(props.dashboard.job.billableWorkUnits || 0), mono: true },
    { label: 'Receipt hash', value: compactIdentifier(props.dashboard.job.computeReceiptHash, 12, 8), mono: true },
    { label: 'Programme Solana', value: compactIdentifier(props.dashboard.devnet?.programId, 12, 8), mono: true },
    { label: 'Transactions Devnet', value: String(props.dashboard.devnet?.signatures?.length || 0), mono: true },
    { label: 'RPC', value: props.dashboard.devnet?.rpc || '—', mono: true },
  ];
});
</script>

<style scoped>
.technical-details{margin:0}.technical-details>div{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr);gap:1rem;padding:.72rem 0;border-bottom:1px solid var(--border)}.technical-details>div:last-child{border:0}.technical-details dt{color:var(--ink-500);font-size:.64rem}.technical-details dd{overflow:hidden;margin:0;color:var(--ink-800);font-size:.68rem;font-weight:650;text-align:right;text-overflow:ellipsis;white-space:nowrap}
</style>
