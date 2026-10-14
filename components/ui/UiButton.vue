<template>
  <NuxtLink v-if="to" :to="to" class="ui-button" :class="classes"><span class="ui-button__sheen" aria-hidden="true"></span>
    <UiIcon v-if="icon" :name="icon" class="ui-button__icon" />
    <slot />
  </NuxtLink>
  <a v-else-if="href" :href="href" :target="target" :rel="target === '_blank' ? 'noopener noreferrer' : undefined" class="ui-button" :class="classes"><span class="ui-button__sheen" aria-hidden="true"></span>
    <UiIcon v-if="icon" :name="icon" class="ui-button__icon" />
    <slot />
  </a>
  <button v-else :type="type" :disabled="disabled || loading" class="ui-button" :class="classes" @click="emit('click', $event)"><span class="ui-button__sheen" aria-hidden="true"></span>
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
.ui-button { position:relative;isolation:isolate;overflow:hidden;display: inline-flex; min-width: max-content; align-items: center; justify-content: center; gap: .55rem; border: 1px solid transparent; border-radius: .82rem; cursor: pointer; font-weight: 760; letter-spacing:-.01em;line-height: 1; transition: transform .28s var(--ease-spring), background-color .25s ease, border-color .25s ease, color .25s ease, box-shadow .28s ease; }
.ui-button>*:not(.ui-button__sheen){position:relative;z-index:1}.ui-button__sheen{position:absolute;z-index:0;top:-80%;bottom:-80%;left:-55%;width:38%;transform:rotate(16deg);background:linear-gradient(90deg,transparent,rgba(255,255,255,.38),transparent);transition:left .65s var(--ease-out);pointer-events:none}.ui-button:hover .ui-button__sheen{left:120%}
.ui-button:hover:not(:disabled) { transform: translateY(-2px); }
.ui-button:active:not(:disabled){transform:translateY(0) scale(.985)}
.ui-button:disabled { cursor: not-allowed; opacity: .55; }
.ui-button--small { min-height: 2.2rem; padding: .55rem .72rem; font-size: .905rem; }
.ui-button--medium { min-height: 2.75rem; padding: .72rem 1rem; font-size: .925rem; }
.ui-button--large { min-height: 3.15rem; padding: .9rem 1.25rem; font-size: .945rem; }
.ui-button--primary { border-color:rgba(255,255,255,.12);background: linear-gradient(145deg,var(--ink-800),var(--ink-950) 62%); color: white; box-shadow:inset 0 1px 0 rgba(255,255,255,.18),inset 0 -1px 0 rgba(0,0,0,.2),0 10px 24px rgba(11,21,35,.2); }
.ui-button--primary:hover { background:linear-gradient(145deg,#283a50,var(--ink-950) 70%);box-shadow:inset 0 1px 0 rgba(255,255,255,.24),0 16px 32px rgba(11,21,35,.24) }
.ui-button--secondary { border-color:var(--glass-edge); background: var(--glass-clear); color: var(--ink-900); box-shadow:var(--glass-inset),0 8px 20px rgba(11,21,35,.06);-webkit-backdrop-filter:blur(16px) saturate(1.25);backdrop-filter:blur(16px) saturate(1.25) }
.ui-button--secondary:hover { border-color:rgba(255,255,255,.95); background: rgba(255,255,255,.94);box-shadow:inset 0 0 0 1px rgba(18,191,174,.2),0 14px 30px rgba(11,21,35,.1) }
.ui-button--ghost { background: transparent; color: var(--ink-700); }
.ui-button--ghost:hover { background: var(--ink-100); color: var(--ink-950); }
.ui-button--danger { border-color: rgba(196,71,71,.18); background: var(--red-100); color: var(--red-600); }
.ui-button__icon { width: 1rem; height: 1rem;transition:transform .28s var(--ease-spring) }.ui-button:hover .ui-button__icon{transform:translateX(2px)}
.ui-button__spinner { width: 1rem; height: 1rem; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: spin .65s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@supports not (backdrop-filter: blur(1px)) { .ui-button--secondary { background: var(--surface); } }
</style>
