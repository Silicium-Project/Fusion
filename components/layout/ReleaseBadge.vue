<template>
  <span
    class="release-badge"
    :class="`release-badge--${normalizedChannel}`"
    data-testid="release-channel"
    :title="build ? `Build ${build}` : undefined"
  >
    <i aria-hidden="true"></i>
    <span>{{ normalizedChannel === 'prod' ? t('release.production') : t('release.development') }}</span>
    <small>{{ version || 'unknown' }}</small>
  </span>
</template>

<script setup lang="ts">
const props = defineProps<{
  channel?: string;
  version?: string;
  build?: string;
}>();

const { t } = useI18n();
const normalizedChannel = computed(() => props.channel?.trim().toLowerCase() === 'prod' ? 'prod' : 'dev');
</script>

<style scoped>
.release-badge{display:inline-flex;align-items:center;gap:.42rem;padding:.36rem .58rem;border:1px solid rgba(122,96,211,.18);border-radius:999px;background:rgba(238,236,255,.72);color:var(--violet-700);font-family:var(--font-mono);font-size:.56rem;font-weight:700;letter-spacing:.02em;white-space:nowrap}.release-badge i{width:.4rem;height:.4rem;border-radius:50%;background:var(--violet-500);box-shadow:0 0 0 .2rem rgba(122,96,211,.1)}.release-badge small{max-width:10rem;overflow:hidden;color:var(--ink-500);font-size:.5rem;font-weight:500;text-overflow:ellipsis}.release-badge--prod{border-color:rgba(18,191,174,.2);background:rgba(225,248,243,.72);color:var(--mint-800)}.release-badge--prod i{background:var(--mint-500);box-shadow:0 0 0 .2rem rgba(18,191,174,.1)}
</style>
