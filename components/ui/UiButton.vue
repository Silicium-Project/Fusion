<template>
  <NuxtLink v-if="to" :to="to" class="ui-button" :class="classes">
    <UiIcon v-if="icon" :name="icon" class="ui-button__icon" />
    <slot />
  </NuxtLink>
  <a v-else-if="href" :href="href" :target="target" :rel="target === '_blank' ? 'noopener noreferrer' : undefined" class="ui-button" :class="classes">
    <UiIcon v-if="icon" :name="icon" class="ui-button__icon" />
    <slot />
  </a>
  <button v-else :type="type" :disabled="disabled || loading" class="ui-button" :class="classes" @click="emit('click', $event)">
    <span v-if="loading" class="ui-button__spinner" aria-hidden="true"></span>
    <UiIcon v-else-if="icon" :name="icon" class="ui-button__icon" />
    <slot />
  </button>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  to?: string | Record<string, unknown>;
  href?: string;
  target?: string;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'small' | 'medium' | 'large';
  icon?: string;
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  loading?: boolean;
}>(), { variant: 'primary', size: 'medium', type: 'button', disabled: false, loading: false });
const emit = defineEmits<{ click: [event: MouseEvent] }>();

const classes = computed(() => [`ui-button--${props.variant}`, `ui-button--${props.size}`]);
</script>

<style scoped>
.ui-button { display: inline-flex; min-width: max-content; align-items: center; justify-content: center; gap: .55rem; border: 1px solid transparent; border-radius: .7rem; cursor: pointer; font-weight: 750; line-height: 1; transition: transform .15s ease, background-color .15s ease, border-color .15s ease, color .15s ease, box-shadow .15s ease; }
.ui-button:hover:not(:disabled) { transform: translateY(-1px); }
.ui-button:disabled { cursor: not-allowed; opacity: .55; }
.ui-button--small { min-height: 2.2rem; padding: .55rem .72rem; font-size: .72rem; }
.ui-button--medium { min-height: 2.75rem; padding: .72rem 1rem; font-size: .78rem; }
.ui-button--large { min-height: 3.15rem; padding: .9rem 1.25rem; font-size: .84rem; }
.ui-button--primary { background: var(--ink-950); color: white; box-shadow: 0 8px 20px rgba(17,27,42,.13); }
.ui-button--primary:hover { background: var(--ink-800); }
.ui-button--secondary { border-color: var(--border-strong); background: white; color: var(--ink-900); }
.ui-button--secondary:hover { border-color: var(--ink-500); background: var(--surface-soft); }
.ui-button--ghost { background: transparent; color: var(--ink-700); }
.ui-button--ghost:hover { background: var(--ink-100); color: var(--ink-950); }
.ui-button--danger { border-color: rgba(196,71,71,.18); background: var(--red-100); color: var(--red-600); }
.ui-button__icon { width: 1rem; height: 1rem; }
.ui-button__spinner { width: 1rem; height: 1rem; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: spin .65s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
