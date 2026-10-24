<template>
  <section class="job-cost-summary surface" :aria-label="t('observability.value.measured')">
    <header><span class="eyebrow">{{ t('observability.value.kicker') }}</span><h2>{{ t('observability.value.measured') }}</h2></header>
    <dl><div><dt>{{ t('observability.value.units') }}</dt><dd>{{ units }}</dd><span v-if="!dashboard.job.computeReceiptHash">{{ t('observability.value.pendingReceipt') }}</span></div><div><dt>{{ t('observability.value.computeTime') }}</dt><dd>{{ duration(dashboard.summary?.performance?.compute_ms) }}</dd></div><div><dt>{{ t('observability.value.networkTime') }}</dt><dd>{{ duration(dashboard.summary?.performance?.network_ms) }}</dd></div><div><dt>{{ t('observability.value.payment') }}</dt><dd>—</dd><span>{{ t('observability.value.paymentMissing') }}</span></div></dl>
    <p>{{ t('observability.value.unitsNote') }}</p>
    <details v-if="dashboard.job.computeReceiptHash"><summary>{{ t('observability.value.receipt') }}<UiIcon name="chevron"/></summary><code>{{ dashboard.job.computeReceiptHash }}</code></details>
  </section>
</template>
<script setup lang="ts">
import type { JobDashboard } from '~/types/api';
import { metricNumber } from '~/utils/telemetry';
import { formatMilliseconds } from '~/utils/format';
import { intlLocale } from '~/utils/i18n';
const props = defineProps<{ dashboard: JobDashboard }>();
const { t } = useI18n();
const units = computed(() => { const value = metricNumber(props.dashboard.job.billableWorkUnits); return props.dashboard.job.computeReceiptHash && value !== null ? new Intl.NumberFormat(intlLocale()).format(value) : '—'; });
const duration = (value: unknown) => metricNumber(value) === null ? '—' : formatMilliseconds(Number(value));
</script>
<style scoped>
.job-cost-summary{padding:1.6rem}.job-cost-summary header{display:flex;flex-direction:column;gap:.5rem}.job-cost-summary h2{margin:0;font-size:1.3rem;font-weight:600;letter-spacing:-.025em}.job-cost-summary dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,8rem),1fr));gap:1.5rem;margin:1.7rem 0}.job-cost-summary dl>div{min-width:0}.job-cost-summary dt{font-size:1rem;color:var(--ink-600);line-height:1.6}.job-cost-summary dd{margin:.6rem 0;font:500 1.6rem/1.3 var(--font-mono);color:var(--ink-950);overflow-wrap:anywhere}.job-cost-summary dl span{font-size:.9375rem;color:var(--ink-600);line-height:1.6}.job-cost-summary>p{max-width:70rem;margin:0;color:var(--ink-600);font-size:1rem;line-height:1.75}.job-cost-summary details{margin-top:1rem;border-top:1px solid var(--border)}.job-cost-summary summary{display:flex;align-items:center;gap:.65rem;min-height:3rem;color:var(--mint-700);cursor:pointer;font-size:1rem;list-style:none}.job-cost-summary summary::-webkit-details-marker{display:none}.job-cost-summary summary svg{width:1rem;transform:rotate(90deg)}.job-cost-summary details[open] svg{transform:rotate(-90deg)}.job-cost-summary code{display:block;padding:.7rem 0;font-size:.9375rem;color:var(--ink-800);line-height:1.7;overflow-wrap:anywhere;user-select:all}
@media(max-width:760px){.job-cost-summary dl{grid-template-columns:repeat(auto-fit,minmax(min(100%,8rem),1fr));gap:1.5rem}.job-cost-summary{padding:1.25rem}}@media(max-width:380px){.job-cost-summary dl{grid-template-columns:1fr}.job-cost-summary dl>div{padding-bottom:1rem;border-bottom:1px solid var(--border)}.job-cost-summary dd{font-size:1.5rem}}
</style>
