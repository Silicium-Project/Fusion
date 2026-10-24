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
.ui-button{overflow-wrap:anywhere;position:relative;isolation:isolate;overflow:hidden;display:inline-flex;min-width:0;align-items:center;justify-content:center;gap:.55rem;border:1px solid transparent;border-radius:.65rem;cursor:pointer;font-weight:550;letter-spacing:-.01em;line-height:1.3;text-align:center;transition:transform .2s ease,background-color .2s,border-color .2s,color .2s,box-shadow .2s}
.ui-button>*:not(.ui-button__sheen){position:relative;z-index:1}.ui-button__sheen{position:absolute;inset:0;z-index:0;pointer-events:none;background:linear-gradient(180deg,rgba(255,255,255,.12),transparent 52%);border-radius:inherit}
.ui-button:hover:not(:disabled){transform:translateY(-1px)}.ui-button:active:not(:disabled){transform:translateY(0)}.ui-button:disabled{cursor:not-allowed;opacity:.55}
.ui-button--small{min-height:2.75rem;padding:.6rem .85rem;font-size:1rem}.ui-button--medium{min-height:2.9rem;padding:.75rem 1.05rem;font-size:1rem}.ui-button--large{min-height:3.2rem;padding:.9rem 1.35rem;font-size:1.0625rem}
.ui-button--primary{border-color:#1d73db;background:linear-gradient(180deg,#388fea,#0965d9);color:white;box-shadow:inset 0 1px 0 rgba(255,255,255,.42),inset 0 -1px 0 rgba(0,45,120,.15),0 4px 12px rgba(30,109,221,.13)}
.ui-button--primary:hover{border-color:#155cbd;background:linear-gradient(180deg,#2d82df,#0759c4);box-shadow:inset 0 1px 0 rgba(255,255,255,.4),0 6px 16px rgba(30,109,221,.17)}
.ui-button--secondary{border-color:var(--glass-edge);background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(247,251,255,.75));color:var(--ink-800);box-shadow:var(--glass-inset),var(--shadow-xs);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}.ui-button--secondary:hover{border-color:#bed4ef;background:white}
.ui-button--ghost{background:transparent;color:var(--ink-700)}.ui-button--ghost .ui-button__sheen{display:none}.ui-button--ghost:hover{background:var(--ink-100);color:var(--ink-950)}
.ui-button--danger{border-color:#f2d3d6;background:var(--red-100);color:var(--red-600)}
.ui-button__icon{width:1rem;height:1rem;flex:none}.ui-button__spinner{width:1rem;height:1rem;flex:none;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin .65s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.ui-button{transition:none}}
</style>
