<template>
  <dl class="technical-details">
    <div v-for="item in items" :key="item.label"><dt>{{ item.label }}</dt><dd :class="{ mono: item.mono }" :title="item.value">{{ item.value }}</dd></div>
  </dl>
</template>

<script setup lang="ts">
import type { JobDashboard } from '~/types/api';
import { compactIdentifier, formatMilliseconds, formatPerformanceMultiple, formatPerformancePercent } from '~/utils/format';
const props = defineProps<{ dashboard: JobDashboard }>();
const { t } = useI18n();
/** A known priority in the user's language, else the raw value. */
const priorityLabel = (priority?: string) => (priority && ['low', 'normal', 'high', 'urgent'].includes(priority) ? t(`jobForm.priorities.${priority}`) : priority || '—');
const items = computed(() => {
  const performance = props.dashboard.summary?.performance;
  return [
    { label: t('technical.networkId'), value: props.dashboard.job.siliciumJobId || '—', mono: true },
    { label: t('technical.workload'), value: props.dashboard.job.workload || '—', mono: false },
    { label: t('technical.priority'), value: priorityLabel(props.dashboard.job.priority), mono: false },
    { label: t('technical.computeTime'), value: formatMilliseconds(performance?.compute_ms), mono: true },
    { label: t('technical.networkTime'), value: formatMilliseconds(performance?.network_ms), mono: true },
    { label: t('technical.computeShare'), value: formatPerformancePercent(performance?.compute_to_total_ratio), mono: true },
    { label: t('technical.computeRatio'), value: formatPerformanceMultiple(performance?.compute_to_network_ratio), mono: true },
    { label: t('technical.billable'), value: String(props.dashboard.job.billableWorkUnits || 0), mono: true },
    { label: t('technical.receipt'), value: compactIdentifier(props.dashboard.job.computeReceiptHash, 12, 8), mono: true },
    { label: t('technical.program'), value: compactIdentifier(props.dashboard.devnet?.programId, 12, 8), mono: true },
    { label: t('technical.transactions'), value: String(props.dashboard.devnet?.signatures?.length || 0), mono: true },
    { label: t('technical.rpc'), value: props.dashboard.devnet?.rpc || '—', mono: true },
  ];
});
</script>

<style scoped>
.technical-details{margin:0}.technical-details>div{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr);gap:1rem;padding:.72rem 0;border-bottom:1px solid var(--border)}.technical-details>div:last-child{border:0}.technical-details dt{color:var(--ink-500);font-size:.877rem}.technical-details dd{overflow:hidden;margin:0;color:var(--ink-800);font-size:.891rem;font-weight:650;text-align:right;text-overflow:ellipsis;white-space:nowrap}
</style>
