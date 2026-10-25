<template>
  <div class="command-snippet" :class="{ 'command-snippet--compact': compact }">
    <div class="command-snippet__bar">
      <span>{{ title }}</span>
      <button type="button" :aria-label="t('experience.repos.copy') + ' — ' + title" @click="copy">
        <UiIcon :name="copied ? 'check' : 'copy'" />
        {{ copied ? t('experience.repos.copied') : t('experience.repos.copy') }}
      </button>
    </div>
    <pre tabindex="0" :aria-label="title"><code>{{ code }}</code></pre>
    <span class="sr-only" role="status">{{ copied ? t('experience.repos.copied') : '' }}</span>
    <p v-if="copyFailed" class="command-snippet__error" role="status">
      {{ t('experience.repos.copyFailed') }}
    </p>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ title: string; code: string; compact?: boolean }>(), {
  compact: false,
});
const { t } = useI18n();
const copied = ref(false);
const copyFailed = ref(false);
let reset: ReturnType<typeof setTimeout> | undefined;
async function copy() {
  try {
    await navigator.clipboard.writeText(props.code);
    copied.value = true;
    copyFailed.value = false;
    if (reset) clearTimeout(reset);
    reset = setTimeout(() => {
      copied.value = false;
    }, 2200);
  } catch {
    copyFailed.value = true;
  }
}
watch(
  () => props.code,
  () => {
    copied.value = false;
    copyFailed.value = false;
  },
);
onBeforeUnmount(() => {
  if (reset) clearTimeout(reset);
});
</script>

<style scoped>
.command-snippet {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #253c5a;
  border-radius: 0.8rem;
  background: #152841;
  color: #ecf3ff;
  box-shadow: inset 0 1px 0 #ffffff0a;
}
.command-snippet__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.6rem 0.9rem;
  border-bottom: 1px solid #ffffff10;
  background: #1a2e48;
}
.command-snippet__bar > span {
  font-family: var(--font-mono);
  font-size: 1rem;
  line-height: 1.6;
  color: #b9cae1;
}
.command-snippet button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2.75rem;
  flex: none;
  padding: 0.4rem 0.7rem;
  border: 1px solid #ffffff30;
  border-radius: 0.5rem;
  background: linear-gradient(#ffffff10, #ffffff05);
  color: #eaf2ff;
  font-size: 1rem;
  cursor: pointer;
  box-shadow: inset 0 1px 0 #ffffff0a;
}
.command-snippet button:hover {
  background: #ffffff16;
}
.command-snippet button svg {
  width: 0.9rem;
  height: 0.9rem;
}
.command-snippet pre {
  min-width: 0;
  overflow: auto;
  margin: 0;
  padding: 1.1rem 1.2rem;
  tab-size: 2;
  scrollbar-color: #6a84a6 #152841;
}
.command-snippet code {
  display: block;
  font-family: var(--font-mono);
  font-size: 1rem;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.command-snippet__error {
  margin: 0;
  padding: 0.7rem 1rem;
  border-top: 1px solid #ffffff20;
  color: #ffe1a3;
  font-size: 1rem;
  line-height: 1.6;
}
.command-snippet--compact pre {
  padding: 0.95rem 1.1rem;
}
@media (max-width: 520px) {
  .command-snippet__bar {
    gap: 0.6rem;
    padding: 0.5rem 0.7rem;
  }
  .command-snippet__bar > span {
    font-size: 1rem;
  }
  .command-snippet pre {
    padding: 1rem 0.85rem;
  }
  .command-snippet code {
    font-size: 1rem;
  }
}
</style>
