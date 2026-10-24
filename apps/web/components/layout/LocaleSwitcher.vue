<template>
  <div class="locale-switcher" role="group" :aria-label="t('language.choose')">
    <button class="locale-switcher__button"
      v-for="item in locales"
      :key="item.code"
      type="button"
      :lang="item.code"
      :title="item.label"
      :aria-label="item.label"
      :aria-pressed="locale === item.code"
      :class="{ 'is-active': locale === item.code }"
      @click="setLocale(item.code)"
    >{{ item.short }}</button>
    <select class="locale-switcher__select" :aria-label="t('language.choose')" :value="locale" @change="selectLocale"><option v-for="item in locales" :key="item.code" :value="item.code" :lang="item.code" :aria-label="item.label">{{ item.short }}</option></select>
  </div>
</template>

<script setup lang="ts">
// Language switcher (FR / EN / DE): the choice is kept in a cookie and the
// API answers in the same language.
const { t, locale, locales, setLocale } = useI18n();
function selectLocale(event: Event) {
  const code = (event.currentTarget as HTMLSelectElement).value;
  if (code === 'fr' || code === 'en' || code === 'de') setLocale(code);
}
</script>

<style scoped>
.locale-switcher{display:inline-flex;align-items:center;gap:.1rem;padding:.2rem;border:1px solid var(--border);border-radius:.7rem;background:rgba(255,255,255,.75)}
.locale-switcher__button{min-width:2.35rem;min-height:2.35rem;padding:.4rem;border:1px solid transparent;border-radius:.5rem;background:transparent;color:var(--ink-500);cursor:pointer;font-size:.9375rem;font-weight:500;transition:background .2s,color .2s}.locale-switcher__button:hover{color:var(--ink-900)}.locale-switcher__button.is-active{border-color:#d7e6f9;background:#edf5ff;color:var(--mint-700);box-shadow:inset 0 1px 0 #fff}.locale-switcher__select{display:none;min-height:2.75rem;padding:.4rem .65rem;border:0;border-radius:.6rem;background:transparent;color:var(--ink-700);font:inherit;font-size:.9375rem;cursor:pointer}
@media(max-width:600px){.locale-switcher{padding:0}.locale-switcher__button{display:none}.locale-switcher__select{display:block;min-width:3.5rem}}
</style>
