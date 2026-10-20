<template>
  <div class="password-input">
    <input v-bind="$attrs" v-model="value" :type="visible ? 'text' : 'password'" class="input password-input__field">
    <button type="button" :aria-label="t(visible ? 'experience.password.hide' : 'experience.password.show')" :title="t(visible ? 'experience.password.hide' : 'experience.password.show')" :aria-pressed="visible" @click="visible = !visible"><UiIcon :name="visible ? 'eye-off' : 'eye'" /></button>
  </div>
</template>
<script setup lang="ts">
defineOptions({ inheritAttrs: false });
const value = defineModel<string>({ default: '' });
const visible = ref(false);
const { t } = useI18n();
watch(value, next => { if (!next) visible.value = false; });
</script>
<style scoped>
.password-input{position:relative;min-width:0}.password-input__field{padding-right:3.25rem}.password-input button{position:absolute;top:50%;right:.2rem;display:grid;width:2.75rem;height:2.75rem;place-items:center;transform:translateY(-50%);border:0;border-radius:.5rem;background:transparent;color:var(--ink-500);cursor:pointer}.password-input button:hover{background:var(--ink-100);color:var(--ink-800)}.password-input button svg{width:1.1rem;height:1.1rem}
</style>
