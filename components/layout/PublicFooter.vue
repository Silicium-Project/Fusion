<template>
  <footer class="public-footer">
    <div class="content-width public-footer__top">
      <div><BrandLogo /><p>Une infrastructure de calcul distribuée, lisible de bout en bout.</p></div>
      <div class="public-footer__links"><strong>Explorer</strong><NuxtLink to="/service">Produit</NuxtLink><NuxtLink to="/about">À propos</NuxtLink><NuxtLink to="/contact">Contact</NuxtLink></div>
      <div class="public-footer__links"><strong>Accès</strong><NuxtLink to="/auth?mode=login">Connexion</NuxtLink><NuxtLink to="/auth?mode=register">Créer un compte</NuxtLink><NuxtLink to="/service#downloads">Téléchargements</NuxtLink></div>
    </div>
    <div class="content-width public-footer__bottom"><span>© {{ new Date().getFullYear() }} Silicium Project</span><span>Devnet · Infrastructure expérimentale</span></div>
  </footer>
</template>

<style scoped>
.public-footer { margin-top: 5rem; border-top: 1px solid var(--border); background: #eef0ec; }
.public-footer__top { display:grid;grid-template-columns:1.7fr .7fr .7fr;gap:3rem;padding-top:3.25rem;padding-bottom:3.25rem }.public-footer__top p{max-width:390px;margin:1rem 0 0;color:var(--ink-600);font-size:.8rem;line-height:1.7}
.public-footer__links { display:grid;align-content:start;gap:.7rem;color:var(--ink-600);font-size:.76rem }.public-footer__links strong{margin-bottom:.2rem;color:var(--ink-950);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em}.public-footer__links a:hover{color:var(--mint-700)}
.public-footer__bottom { display:flex;justify-content:space-between;padding-top:1.25rem;padding-bottom:1.25rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.68rem }
@media(max-width:700px){.public-footer__top{grid-template-columns:1fr 1fr;gap:2rem}.public-footer__top>div:first-child{grid-column:1/-1}.public-footer__bottom{align-items:flex-start;flex-direction:column;gap:.4rem}}
</style>
