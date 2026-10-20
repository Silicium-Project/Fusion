<template>
  <ol class="execution-timeline">
    <li v-for="item in steps" :key="item.label" :class="`execution-timeline--${item.state}`"><span><UiIcon :name="item.state === 'done' ? 'check' : item.state === 'failed' ? 'x' : item.icon"/></span><div><strong>{{ item.label }}</strong><small>{{ item.detail }}</small></div></li>
  </ol>
</template>

<script setup lang="ts">
import type { JobDashboard } from '~/types/api';
import { formatDate } from '~/utils/format';
import { fragmentVisualState } from '~/utils/jobs';
const props = defineProps<{ dashboard: JobDashboard }>();
const { t } = useI18n();
const terminal = computed(() => ['completed','failed','cancelled','expired'].includes(props.dashboard.job.status));
const fragments = computed(() => props.dashboard.summary?.fragments || []);
const completedFragments = computed(() => fragments.value.filter(fragment => fragmentVisualState(fragment.status) === 'done').length);
const computingFragments = computed(() => fragments.value.filter(fragment => fragmentVisualState(fragment.status) === 'computing').length);
const validatingFragments = computed(() => fragments.value.filter(fragment => fragmentVisualState(fragment.status) === 'validating').length);
const totalFragments = computed(() => Number(props.dashboard.summary?.fragmentCount || props.dashboard.job.fragmentCount || props.dashboard.summary?.fragments?.length || 0));
const calculationDone = computed(() => totalFragments.value > 0 && completedFragments.value === totalFragments.value);
const steps = computed(() => [
  { label: t('timeline.received'), detail: formatDate(props.dashboard.job.createdAt), state: 'done', icon: 'upload' },
  { label: t('timeline.orchestration'), detail: props.dashboard.job.startedAt ? formatDate(props.dashboard.job.startedAt) : t('timeline.awaiting'), state: props.dashboard.job.startedAt ? 'done' : 'current', icon: 'layers' },
  { label: t('timeline.computing'), detail: computingFragments.value ? t('timeline.computingDetail', { count: computingFragments.value, done: completedFragments.value, total: totalFragments.value || '—' }) : t('timeline.doneDetail', { count: completedFragments.value, total: totalFragments.value || '—' }), state: props.dashboard.job.status === 'failed' ? 'failed' : calculationDone.value || props.dashboard.resultReady ? 'done' : props.dashboard.job.startedAt ? 'current' : 'pending', icon: 'processor' },
  { label: t('timeline.verification'), detail: props.dashboard.resultReady ? t('timeline.ready') : validatingFragments.value ? t('timeline.validating', { count: validatingFragments.value }) : props.dashboard.job.status === 'completed' ? t('timeline.fetching') : terminal.value ? t('timeline.interrupted') : t('timeline.upcoming'), state: props.dashboard.resultReady ? 'done' : props.dashboard.job.status === 'failed' ? 'failed' : validatingFragments.value || props.dashboard.job.status === 'completed' ? 'current' : 'pending', icon: 'shield' },
]);
</script>

<style scoped>
.execution-timeline{display:grid;margin:0;padding:0;list-style:none}.execution-timeline li{position:relative;display:grid;min-height:66px;grid-template-columns:2rem 1fr;gap:.75rem}.execution-timeline li:not(:last-child)::after{position:absolute;top:2rem;bottom:0;left:.98rem;width:1px;background:var(--border);content:''}.execution-timeline li>span{z-index:1;display:grid;width:2rem;height:2rem;place-items:center;border:1px solid var(--border);border-radius:.6rem;background:white;color:var(--ink-400)}.execution-timeline svg{width:.85rem}.execution-timeline strong,.execution-timeline small{display:block}.execution-timeline strong{padding-top:.1rem;font-size:.9375rem}.execution-timeline small{margin-top:.25rem;color:var(--ink-500);font-size:.9375rem;line-height:1.4}.execution-timeline--done>span{border-color:rgba(32,124,93,.14)!important;background:var(--green-100)!important;color:var(--green-600)!important}.execution-timeline--current>span{border-color:rgba(13,149,136,.15)!important;background:var(--mint-100)!important;color:var(--mint-700)!important}.execution-timeline--failed>span{border-color:rgba(196,71,71,.15)!important;background:var(--red-100)!important;color:var(--red-600)!important}.execution-timeline--pending{opacity:.6}
</style>
