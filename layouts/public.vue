<template>
  <div class="public-layout"><PublicHeader /><main><slot /></main><PublicFooter /></div>
</template>

<style scoped>
.public-layout{min-height:100vh;overflow:hidden;background:radial-gradient(circle at 82% 8%,rgba(24,181,165,.06),transparent 22%),radial-gradient(circle at 12% 32%,rgba(117,104,232,.045),transparent 22%),var(--paper-warm)}
</style>
