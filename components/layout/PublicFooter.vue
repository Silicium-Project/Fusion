<template>
  <footer class="public-footer">
    <div class="marketing-container public-footer__top">
      <div class="public-footer__brand"><BrandLogo /><p>Silicium donne à vos projets accès à plusieurs machines, puis vous rend un résultat vérifié.</p></div>
      <div class="public-footer__links"><strong>Explorer</strong><NuxtLink to="/service">Produit</NuxtLink><NuxtLink to="/download">Télécharger le nœud</NuxtLink><NuxtLink to="/blockchain">Blockchain</NuxtLink><NuxtLink to="/about">À propos</NuxtLink><NuxtLink to="/contact">Idées</NuxtLink></div>
      <div class="public-footer__links"><strong>Accès</strong><NuxtLink to="/auth?mode=login">Connexion</NuxtLink><NuxtLink to="/auth?mode=register">Ouvrir un compte</NuxtLink><NuxtLink to="/download">Installer une machine</NuxtLink></div>
      <div class="public-footer__status"><span class="public-footer__status-dot"></span><div><strong>Devnet opérationnel</strong><small>Infrastructure expérimentale</small></div></div>
    </div>
    <div class="marketing-container public-footer__bottom"><span>© {{ new Date().getFullYear() }} Silicium Project</span><span>Conçu pour rendre le calcul vérifiable.</span></div>
  </footer>
</template>

<style scoped>
.public-footer{margin-top:6rem;border-top:1px solid var(--border);background:rgba(235,240,237,.55)}
.public-footer__top{display:grid;grid-template-columns:1.7fr .65fr .65fr .9fr;gap:2.5rem;padding-block:3.6rem}
.public-footer__brand p{max-width:350px;margin:1rem 0 0;color:var(--ink-700);font-size:.86rem;line-height:1.72}
.public-footer__links{display:grid;align-content:start;gap:.65rem;color:var(--ink-700);font-size:.78rem}.public-footer__links strong{margin-bottom:.3rem;color:var(--ink-900);font-size:.65rem;letter-spacing:.12em;text-transform:uppercase}.public-footer__links a:hover{color:var(--mint-700)}
.public-footer__status{display:flex;align-items:flex-start;gap:.65rem;align-self:start;padding:.85rem;border:1px solid rgba(255,255,255,.8);border-radius:.9rem;background:rgba(255,255,255,.5);box-shadow:inset 0 0 0 1px var(--border)}.public-footer__status-dot{width:.48rem;height:.48rem;margin-top:.22rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .25rem rgba(18,191,174,.12)}.public-footer__status strong,.public-footer__status small{display:block}.public-footer__status strong{font-size:.7rem}.public-footer__status small{margin-top:.2rem;color:var(--ink-500);font-size:.62rem;line-height:1.4}
.public-footer__bottom{display:flex;justify-content:space-between;padding-block:1.2rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.68rem}
@media(max-width:900px){.public-footer__top{grid-template-columns:1.4fr .8fr .8fr}.public-footer__status{grid-column:1/-1;justify-self:start}}
@media(max-width:620px){.public-footer{margin-top:4rem}.public-footer__top{grid-template-columns:1fr 1fr;gap:2.25rem;padding-block:2.75rem}.public-footer__brand{grid-column:1/-1}.public-footer__status{grid-column:1/-1}.public-footer__bottom{align-items:flex-start;flex-direction:column;gap:.45rem}}
</style>
