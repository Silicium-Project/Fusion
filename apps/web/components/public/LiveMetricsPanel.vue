<template>
  <section class="live-metrics-panel marketing-glass" :aria-label="t('observability.telemetry.title')">
    <header><h2>{{ t('observability.telemetry.title') }}</h2><UiStatusBadge :status="status?.network.status || 'unknown'"/></header>
    <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
    <dl class="live-metrics-panel__metrics"><div v-for="item in metrics" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl>
    <dl class="live-metrics-panel__resources"><div><dt>{{ t('observability.telemetry.cpu') }}</dt><dd>{{ percent(status?.network.systemCpuPercent) }}</dd></div><div><dt>{{ t('observability.telemetry.memory') }}</dt><dd>{{ percent(status?.network.systemMemoryPercent) }}</dd></div></dl>
    <TelemetryTrend :title="t('observability.telemetry.queueChart')" :samples="samples" mode="tasks"/>
    <footer><span>{{ t('observability.telemetry.observed') }} · {{ checkedAt }}</span><NuxtLink to="/service#status">{{ t('observability.telemetry.view') }}<UiIcon name="arrow"/></NuxtLink></footer>
  </section>
</template>
<script setup lang="ts">
import { metricNumber, metricPercent } from '~/utils/telemetry';
import { intlLocale } from '~/utils/i18n';
const { t } = useI18n();
const { status, error, loading, refresh } = useSystemStatus();
const { samples, record } = useTelemetryHistory();
const available = computed(() => status.value && !['unknown', 'unavailable'].includes(status.value.network.status));
const display = (value: unknown) => available.value && metricNumber(value) !== null ? new Intl.NumberFormat(intlLocale()).format(Number(value)) : '—';
const percent = (value: unknown) => available.value && metricPercent(value) !== null ? `${new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 1 }).format(Number(value))} %` : '—';
const metrics = computed(() => [
  { label: t('observability.telemetry.online'), value: display(status.value?.network.activePeers) },
  { label: t('observability.telemetry.active'), value: display(status.value?.network.activeTasks) },
  { label: t('observability.telemetry.queue'), value: display(status.value?.network.queueDepth) },
]);
const checkedAt = computed(() => status.value?.checkedAt && available.value ? new Intl.DateTimeFormat(intlLocale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(status.value.checkedAt)) : '—');
watch(() => status.value, current => {
  if (!import.meta.client || !current) return;
  record({ at: Date.parse(current.checkedAt), cpu: null, memory: null, queue: available.value ? metricNumber(current.network.queueDepth) : null, active: available.value ? metricNumber(current.network.activeTasks) : null });
}, { immediate: true });
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { if (!status.value && !loading.value) refresh(); timer = setInterval(() => { if (document.visibilityState === 'visible' && !loading.value) refresh(); }, 10_000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); });
</script>
<style scoped>
.live-metrics-panel__resources{display:flex;flex-wrap:wrap;gap:1rem 2rem;margin:-.6rem 0 1.8rem;padding-bottom:1.2rem;border-bottom:1px solid var(--border)}.live-metrics-panel__resources>div{display:flex;gap:.65rem;align-items:baseline}.live-metrics-panel__resources dd{margin:0;font-size:1rem;letter-spacing:0}.live-metrics-panel__resources dt{font-size:1rem}

.live-metrics-panel{min-width:0;padding:1.5rem;border-radius:1.2rem}.live-metrics-panel>header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem}.live-metrics-panel h2{margin:0;font-size:1.15rem;font-weight:600;line-height:1.4;letter-spacing:-.025em}.live-metrics-panel__metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin:1.8rem 0 2rem}.live-metrics-panel__metrics>div{min-width:0;border-right:1px solid var(--border);padding-right:.5rem}.live-metrics-panel__metrics>div:last-child{border:0}.live-metrics-panel dt{color:var(--ink-600);font-size:.9375rem;line-height:1.5}.live-metrics-panel dd{margin:.65rem 0 0;color:var(--ink-950);font:500 1.8rem/1.2 var(--font-mono);letter-spacing:-.04em}.live-metrics-panel>footer{display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;gap:.75rem;margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--border);font-size:.9375rem;color:var(--ink-600)}.live-metrics-panel>footer a{display:flex;align-items:center;gap:.5rem;color:var(--mint-700);min-height:2.75rem}.live-metrics-panel>footer svg{width:1rem}.live-metrics-panel :deep(.telemetry-trend__head>span){display:none}.live-metrics-panel :deep(.telemetry-trend footer){font-size:.9375rem}.live-metrics-panel :deep(.telemetry-trend footer>span){display:none}
@media(max-width:540px){.live-metrics-panel{padding:1.15rem}.live-metrics-panel__metrics{gap:.7rem}.live-metrics-panel dd{font-size:1.55rem}.live-metrics-panel__metrics dt{font-size:.9375rem}}
</style>
