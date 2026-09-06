<template>
  <div class="auth-layout"><div class="auth-layout__brand"><BrandLogo /></div><slot /></div>
</template>

<style scoped>
.auth-layout{position:relative;min-height:100vh;overflow:hidden;background:radial-gradient(circle at 78% 12%,rgba(24,181,165,.09),transparent 26%),radial-gradient(circle at 12% 86%,rgba(117,104,232,.075),transparent 25%),var(--paper-warm)}.auth-layout::before{position:absolute;inset:0;opacity:.35;background-image:linear-gradient(rgba(23,34,49,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(23,34,49,.035) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(125deg,#000,transparent 78%);content:''}.auth-layout__brand{position:absolute;top:1.5rem;left:clamp(1rem,4vw,3.5rem);z-index:3}
</style>
