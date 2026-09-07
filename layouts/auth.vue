<template>
  <div class="auth-layout"><div class="auth-layout__material" aria-hidden="true"></div><div class="auth-layout__brand"><BrandLogo /></div><slot /></div>
</template>

<style scoped>
.auth-layout{position:relative;min-height:100vh;overflow:hidden;background:var(--paper-warm)}.auth-layout::before{position:absolute;inset:0;opacity:.38;background:linear-gradient(rgba(21,40,61,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(21,40,61,.04) 1px,transparent 1px);background-size:5rem 5rem;mask-image:linear-gradient(125deg,#000,transparent 82%);content:''}.auth-layout__material{position:absolute;top:0;right:0;width:min(50vw,42rem);height:36rem;background:radial-gradient(circle at 70% 10%,rgba(18,191,174,.16),transparent 68%);filter:blur(18px);opacity:.75}.auth-layout__brand{position:absolute;top:1.5rem;left:clamp(1rem,4vw,3.5rem);z-index:3}
</style>
