<template>
  <NuxtLink to="/service#status" class="network-status-strip" :aria-label="t('experience.live.view')">
    <span class="network-status-strip__state"><span>{{ t('experience.live.label') }}</span><UiStatusBadge :status="status?.network.status || 'unknown'" /></span>
    <span v-if="available" class="network-status-strip__peers"><strong>{{ status?.network.activePeers }}</strong>{{ t('experience.live.peers') }}</span>
    <span v-if="status?.checkedAt" class="network-status-strip__time">{{ t('experience.live.checked') }} · {{ time }}</span>
    <span class="network-status-strip__link">{{ t('experience.live.view') }}<UiIcon name="arrow" /></span>
  </NuxtLink>
</template>

<script setup lang="ts">
import { intlLocale } from '~/utils/i18n';
const { t } = useI18n();
const { status } = useSystemStatus();
const available = computed(() => status.value && !['unavailable', 'unknown'].includes(status.value.network.status));
const time = computed(() => status.value?.status === 'unavailable' ? t('experience.live.unavailable') : status.value?.checkedAt ? new Intl.DateTimeFormat(intlLocale(), { hour: '2-digit', minute: '2-digit' }).format(new Date(status.value.checkedAt)) : '—');
</script>

<style scoped>
.network-status-strip{display:flex;align-items:center;gap:1.4rem;min-height:4rem;padding:.9rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);font-size:.9375rem;color:var(--ink-600)}
.network-status-strip__state{display:flex;align-items:center;gap:.7rem}.network-status-strip__state>span{font-weight:550;color:var(--ink-800)}.network-status-strip__peers{display:flex;gap:.45rem}.network-status-strip__peers strong{color:var(--ink-800);font-weight:550}.network-status-strip__time{margin-left:auto;color:var(--ink-500);font-size:.9375rem}.network-status-strip__link{display:flex;align-items:center;gap:.6rem;margin-left:auto;color:var(--mint-700);font-size:.9375rem;font-weight:500}.network-status-strip__link svg{width:.9rem}
@media(max-width:760px){.network-status-strip__time{display:none}}
@media(max-width:540px){.network-status-strip{flex-wrap:wrap;column-gap:1rem;row-gap:.7rem;font-size:.9375rem}.network-status-strip__peers{display:none}.network-status-strip__link{font-size:.9375rem}.network-status-strip__state{gap:.55rem}}
</style>
