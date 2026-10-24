<template>
  <section class="network-monitor surface" :class="{ 'network-monitor--compact': compact }" :aria-label="t('observability.telemetry.networkResources')">
    <header><div><h2>{{ t('observability.telemetry.title') }}</h2><p>{{ t('observability.telemetry.poll', { seconds: 5 }) }}</p></div><span>{{ t('observability.telemetry.observed') }} · {{ updatedLabel }}</span></header>
    <p v-if="stale" class="network-monitor__stale">{{ t('observability.telemetry.stale') }}</p>
    <dl class="network-monitor__metrics"><div v-for="item in metrics" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
    <TelemetryTrend :title="t('observability.telemetry.networkResources')" :samples="samples"/>
    <p class="network-monitor__scope">{{ t('observability.telemetry.snapshot') }}</p>
    <section v-if="!compact" class="network-monitor__roles"><header><h3>{{ t('observability.telemetry.roles') }}</h3><NuxtLink to="/nodes">{{ t('observability.worker.nodes') }}<UiIcon name="arrow"/></NuxtLink></header><dl><div v-for="role in roles" :key="role.key"><dt>{{ role.label }}</dt><dd>{{ lastUpdatedAt ? role.count : '—' }}</dd></div></dl><p>{{ t('observability.telemetry.rolesNote') }}</p></section>
  </section>
</template>
<script setup lang="ts">
import type { NetworkMetrics } from '~/types/api';
import { formatDate, networkRoleGroup, type NetworkRoleGroup } from '~/utils/format';
import { metricNumber, metricPercent } from '~/utils/telemetry';
import { intlLocale } from '~/utils/i18n';
const props = defineProps<{ totalNodes?: number; activeNodes?: number; activeWorkloads?: number; roleGroups?: { role: string; count: number }[]; networkMetrics?: NetworkMetrics; lastUpdatedAt?: string | null; compact?: boolean; stale?: boolean }>();
const { t } = useI18n();
const { samples, record } = useTelemetryHistory();
const display = (value: unknown) => props.lastUpdatedAt && metricNumber(value) !== null ? new Intl.NumberFormat(intlLocale()).format(Number(value)) : '—';
const metrics = computed(() => [
  { label: t('observability.telemetry.online'), value: display(props.activeNodes) },
  { label: t('observability.telemetry.active'), value: display(props.networkMetrics?.active_tasks) },
  { label: t('observability.telemetry.queue'), value: display(props.networkMetrics?.queue_depth) },
  { label: t('observability.telemetry.instrumented'), value: display(props.networkMetrics?.telemetry_nodes) },
]);
const updatedLabel = computed(() => props.lastUpdatedAt ? formatDate(props.lastUpdatedAt) : '—');
const roles = computed(() => (['compute','verify','storage','orchestration'] as NetworkRoleGroup[]).map(key => ({ key, label: t(`roles.${key}`), count: (props.roleGroups || []).filter(group => networkRoleGroup(group.role) === key).reduce((sum, group) => sum + group.count, 0) })));
watch(() => props.lastUpdatedAt, at => {
  if (!import.meta.client || !at || props.stale) return;
  record({ at: Date.parse(at), cpu: metricPercent(props.networkMetrics?.system_cpu_percent), memory: metricPercent(props.networkMetrics?.system_memory_percent), queue: metricNumber(props.networkMetrics?.queue_depth), active: metricNumber(props.networkMetrics?.active_tasks) });
}, { immediate: true });
</script>
<style scoped>
.network-monitor{min-width:0;padding:1.7rem}.network-monitor>header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem}.network-monitor h2{margin:0;font-size:1.3rem;letter-spacing:-.025em;font-weight:600}.network-monitor>header p{margin:.5rem 0 0;color:var(--ink-600);font-size:1rem}.network-monitor>header>span{color:var(--ink-600);font-size:.9375rem;line-height:1.7}.network-monitor__stale{padding:1rem;border-radius:.7rem;background:var(--amber-100);color:var(--amber-600);font-size:1rem;line-height:1.6}.network-monitor__metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.5rem;margin:2rem 0;padding-bottom:2rem;border-bottom:1px solid var(--border)}.network-monitor__metrics>div{padding-left:1.5rem;border-left:1px solid var(--border)}.network-monitor__metrics>div:first-child{padding-left:0;border:0}.network-monitor dt{font-size:1rem;color:var(--ink-600);line-height:1.5}.network-monitor dd{margin:.75rem 0 0;font:500 2rem/1.2 var(--font-mono);color:var(--ink-950)}.network-monitor__scope{margin:1.4rem 0 0;color:var(--ink-600);font-size:.9375rem;line-height:1.7}.network-monitor__roles{margin-top:2rem;padding-top:1.7rem;border-top:1px solid var(--border)}.network-monitor__roles header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem}.network-monitor__roles h3{margin:0;font-size:1.2rem;font-weight:600}.network-monitor__roles a{display:flex;align-items:center;gap:.6rem;min-height:2.75rem;color:var(--mint-700);font-size:1rem}.network-monitor__roles svg{width:1rem}.network-monitor__roles dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1.5rem;margin:1.5rem 0}.network-monitor__roles dd{font-size:1.6rem}.network-monitor__roles p{margin:0;color:var(--ink-600);font-size:1rem;line-height:1.7}
@media(max-width:650px){.network-monitor{padding:1.25rem}.network-monitor__metrics,.network-monitor__roles dl{grid-template-columns:1fr 1fr;gap:1.5rem 1rem}.network-monitor__metrics>div{padding-left:1rem}.network-monitor__metrics>div:nth-child(3){padding-left:0;border-left:0}.network-monitor dd{font-size:1.8rem}}
</style>
