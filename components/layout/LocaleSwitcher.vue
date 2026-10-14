<template>
  <div class="locale-switcher" role="group" :aria-label="t('language.choose')">
    <button
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
  </div>
</template>

<script setup lang="ts">
// Language switcher (FR / EN / DE): the choice is kept in a cookie and the
// API answers in the same language.
const { t, locale, locales, setLocale } = useI18n();
</script>

<style scoped>
.locale-switcher{display:inline-flex;align-items:center;gap:.1rem;padding:.16rem;border:1px solid var(--border);border-radius:999px;background:rgba(255,255,255,.62)}
.locale-switcher button{min-width:1.9rem;height:1.55rem;padding:0 .4rem;border:0;border-radius:999px;background:transparent;color:var(--ink-500);cursor:pointer;font-family:var(--font-mono);font-size:.857rem;font-weight:700;letter-spacing:.04em;transition:background-color .2s,color .2s}
.locale-switcher button:hover{color:var(--ink-900)}
.locale-switcher button.is-active{background:var(--ink-900);color:white}
.locale-switcher button:focus-visible{outline:2px solid var(--mint-500);outline-offset:1px}
</style>
