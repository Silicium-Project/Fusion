<template>
  <label class="scene-slider">
    <span class="scene-slider__label"
      >{{ label }}<small v-if="hint">{{ hint }}</small></span
    >
    <input
      class="scene-slider__range"
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :value="clamped"
      :aria-label="label"
      @input="onInput"
    />
    <input
      class="scene-slider__number"
      type="number"
      :min="min"
      :max="max"
      :step="step"
      :value="display"
      :aria-label="label"
      @change="onInput"
    />
  </label>
</template>

<script setup lang="ts">
// A labelled slider with a number field, for one value of the scene editor.
// The number field accepts values beyond the slider's range.
const props = withDefaults(
  defineProps<{ label: string; min: number; max: number; step?: number; hint?: string }>(),
  { step: 0.1, hint: '' },
);
const model = defineModel<number>({ required: true });
const clamped = computed(() => Math.min(props.max, Math.max(props.min, model.value)));
const decimals = computed(() => (String(props.step).split('.')[1] || '').length);
const display = computed(() => Number(model.value.toFixed(decimals.value)));
function onInput(event: Event) {
  const value = Number((event.target as HTMLInputElement).value);
  if (Number.isFinite(value)) model.value = value;
}
</script>

<style scoped>
.scene-slider {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 4.6rem;
  align-items: center;
  gap: 0.25rem 0.6rem;
}
.scene-slider__label {
  grid-column: 1/-1;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  color: var(--ink-700);
  font-size: 0.9375rem;
  font-weight: 650;
}
.scene-slider__label small {
  color: var(--ink-500);
  font-weight: 500;
}
.scene-slider__range {
  width: 100%;
  accent-color: var(--mint-600);
}
.scene-slider__number {
  width: 100%;
  padding: 0.3rem 0.4rem;
  border: 1px solid var(--border-strong);
  border-radius: 0.45rem;
  background: white;
  color: var(--ink-900);
  font-family: var(--font-mono);
  font-size: 0.9375rem;
}
</style>
