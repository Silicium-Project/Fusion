<template>
  <span class="status-badge" :class="`status-badge--${resolvedTone}`">
    <span class="status-badge__dot" aria-hidden="true"></span>
    {{ label || statusLabel(status) }}
  </span>
</template>

<script setup lang="ts">
import { statusLabel, statusTone } from '~/utils/format';
const props = defineProps<{ status?: string; label?: string; tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>();
const resolvedTone = computed(() => props.tone || statusTone(props.status));
</script>

<style scoped>
.status-badge { display: inline-flex; width: max-content; align-items: center; gap: .42rem; border-radius: 999px; padding: .34rem .58rem; font-size: .884rem; font-weight: 800; line-height: 1; white-space: nowrap; }
.status-badge__dot { width: .38rem; height: .38rem; border-radius: 50%; background: currentColor; }
.status-badge--success { background: var(--green-100); color: var(--green-600); }
.status-badge--warning { background: var(--amber-100); color: var(--amber-600); }
.status-badge--danger { background: var(--red-100); color: var(--red-600); }
.status-badge--info { background: var(--mint-100); color: var(--mint-700); }
.status-badge--neutral { background: var(--ink-100); color: var(--ink-700); }
</style>
