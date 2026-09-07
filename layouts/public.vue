<template>
  <div v-spatial class="public-layout">
    <div class="public-layout__material" aria-hidden="true"></div>
    <PublicHeader />
    <main><slot /></main>
    <PublicFooter />
  </div>
</template>

<style scoped>
.public-layout{position:relative;min-height:100vh;background:var(--paper-warm)}
.public-layout__material{position:fixed;z-index:0;inset:0;pointer-events:none;background:linear-gradient(120deg,rgba(255,255,255,.38),transparent 36%),linear-gradient(300deg,rgba(222,248,244,.17),transparent 42%);opacity:.9}
.public-layout main,.public-layout :deep(.public-footer){position:relative;z-index:1}
</style>
