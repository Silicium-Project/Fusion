<template>
  <div class="auth-layout"><div class="auth-layout__material" aria-hidden="true"></div><div class="auth-layout__brand"><BrandLogo /></div><LocaleSwitcher class="auth-layout__locale" /><slot /></div>
</template>

<style scoped>
.auth-layout{position:relative;min-height:100vh;overflow:clip;background:var(--paper-warm)}.auth-layout::before,.auth-layout__material{display:none}.auth-layout__brand{position:absolute;top:1.6rem;left:clamp(1rem,4vw,3.5rem);z-index:3}.auth-layout__locale{position:absolute;top:1.8rem;right:clamp(1rem,4vw,3.5rem);z-index:3}
</style>
