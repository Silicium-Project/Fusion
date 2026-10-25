<template>
  <div class="notice" :class="`notice--${tone}`" :role="tone === 'danger' ? 'alert' : 'status'">
    <UiIcon
      :name="tone === 'danger' ? 'alert' : tone === 'success' ? 'check' : 'activity'"
      class="notice__icon"
    />
    <div>
      <strong v-if="title">{{ title }}</strong>
      <p><slot /></p>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'info' | 'success' | 'warning' | 'danger'; title?: string }>(), {
  tone: 'info',
});
</script>

<style scoped>
.notice {
  display: flex;
  gap: 0.75rem;
  border: 1px solid;
  border-radius: var(--radius-md);
  padding: 0.85rem 1rem;
  font-size: 0.9375rem;
  line-height: 1.5;
}
.notice p {
  margin: 0.12rem 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.notice__icon {
  width: 1.05rem;
  height: 1.05rem;
  flex: 0 0 auto;
  margin-top: 0.1rem;
}
.notice--info {
  border-color: rgba(13, 149, 136, 0.2);
  background: var(--mint-100);
  color: var(--mint-700);
}
.notice--success {
  border-color: rgba(32, 124, 93, 0.2);
  background: var(--green-100);
  color: var(--green-600);
}
.notice--warning {
  border-color: rgba(196, 105, 23, 0.2);
  background: var(--amber-100);
  color: var(--amber-600);
}
.notice--danger {
  border-color: rgba(196, 71, 71, 0.2);
  background: var(--red-100);
  color: var(--red-600);
}
</style>
