<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" role="presentation" @mousedown.self="$emit('close')">
        <section class="modal-panel" role="dialog" aria-modal="true" :aria-labelledby="titleId">
          <header class="modal-panel__header">
            <h2 :id="titleId">{{ title }}</h2>
            <button type="button" :aria-label="t('common.close')" @click="$emit('close')">
              <UiIcon name="x" />
            </button>
          </header>
          <div class="modal-panel__body"><slot /></div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
const props = defineProps<{ open: boolean; title: string }>();
const { t } = useI18n();
const titleId = `modal-${Math.random().toString(36).slice(2)}`;

function onKeydown(event: KeyboardEvent) {
  if (props.open && event.key === 'Escape') emitClose();
}
const emit = defineEmits<{ close: [] }>();
function emitClose() {
  emit('close');
}

watch(
  () => props.open,
  (value) => {
    if (import.meta.client) document.body.style.overflow = value ? 'hidden' : '';
  },
);
onMounted(() => window.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
  document.body.style.overflow = '';
});
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  overflow-y: auto;
  padding: 1rem;
  background: rgba(17, 27, 42, 0.42);
  backdrop-filter: blur(8px);
}
.modal-panel {
  width: min(100%, 620px);
  max-height: calc(100vh - 2rem);
  overflow: auto;
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 1.25rem;
  background: white;
  box-shadow: 0 28px 90px rgba(17, 27, 42, 0.2);
}
.modal-panel__header {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.25rem;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(12px);
}
.modal-panel__header h2 {
  margin: 0;
  font-size: 1.05rem;
  letter-spacing: -0.025em;
}
.modal-panel__header button {
  display: grid;
  width: 2.2rem;
  height: 2.2rem;
  place-items: center;
  border: 0;
  border-radius: 0.55rem;
  background: var(--ink-100);
  cursor: pointer;
}
.modal-panel__header svg {
  width: 1rem;
}
.modal-panel__body {
  padding: 1.25rem;
}
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.16s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-active .modal-panel,
.modal-leave-active .modal-panel {
  transition: transform 0.16s ease;
}
.modal-enter-from .modal-panel,
.modal-leave-to .modal-panel {
  transform: translateY(8px) scale(0.985);
}
</style>
