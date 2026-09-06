<template>
  <div>
    <section class="hero content-width">
      <div class="hero__copy">
        <div class="hero__eyebrow"><span></span> Infrastructure distribuée · Devnet</div>
        <h1>Votre réseau.<br><em>Une seule puissance.</em></h1>
        <p>Silicium transforme des machines hétérogènes en une infrastructure de calcul coordonnée, observable et vérifiable.</p>
        <div class="hero__actions"><UiButton :to="primaryTarget" size="large" icon="arrow">{{ isAuthenticated ? 'Ouvrir mon espace' : 'Commencer maintenant' }}</UiButton><UiButton to="/service" variant="secondary" size="large">Découvrir le fonctionnement</UiButton></div>
        <div class="hero__proof"><span><UiIcon name="shield"/>Résultats vérifiés</span><span><UiIcon name="network"/>Distribution pair-à-pair</span><span><UiIcon name="activity"/>Suivi en temps réel</span></div>
      </div>
      <NetworkIllustration />
    </section>

    <section class="principles content-width" aria-label="Principes du produit">
      <article v-for="principle in principles" :key="principle.title"><div><UiIcon :name="principle.icon"/></div><span class="eyebrow">{{ principle.number }}</span><h2>{{ principle.title }}</h2><p>{{ principle.text }}</p></article>
    </section>

    <section class="flow-section content-width">
      <div class="section-heading"><div><span class="eyebrow">Du fichier au résultat</span><h2>Un flux lisible, même quand le réseau grandit.</h2></div><p>Chaque étape dispose d’un rôle clair. L’interface expose les décisions utiles sans transformer l’exploitation en tableau de bord d’ingénieur.</p></div>
      <ProcessFlow />
    </section>

    <section class="feature content-width">
      <div class="feature__visual">
        <div class="feature__window"><header><span></span><span></span><span></span><strong>Exécution · rendu-architecture</strong></header><div class="feature__window-body"><div class="feature__line"><span class="success"><UiIcon name="check"/></span><div><strong>Entrée acceptée</strong><small>scene-v4.cfg · 08:42:11</small></div></div><div class="feature__line"><span><UiIcon name="layers"/></span><div><strong>64 fragments distribués</strong><small>5 nœuds de calcul · 2 vérificateurs</small></div></div><div class="feature__line"><span class="violet"><UiIcon name="shield"/></span><div><strong>Attestations contrôlées</strong><small>64 / 64 reçues et valides</small></div></div><div class="feature__result"><UiIcon name="result"/><div><strong>Résultat disponible</strong><small>PNG · 4K · hash vérifié</small></div><UiIcon name="download"/></div></div></div>
      </div>
      <div class="feature__copy"><span class="eyebrow">Confiance opérationnelle</span><h2>Comprendre ce qui se passe. Agir au bon moment.</h2><p>Les tâches, nœuds, preuves et résultats partagent une seule grammaire visuelle. Les détails techniques restent accessibles, mais ne prennent jamais le dessus sur l’action.</p><ul><li><UiIcon name="check"/>Statuts cohérents sur tout le produit</li><li><UiIcon name="check"/>Réseau agrégé puis exploré à la demande</li><li><UiIcon name="check"/>Traçabilité Devnet rattachée à chaque exécution</li></ul><UiButton to="/about" variant="secondary" icon="arrow">Notre approche</UiButton></div>
    </section>

    <section class="final-cta content-width"><div><span class="eyebrow">Prêt à distribuer</span><h2>Votre prochaine exécution commence ici.</h2><p>Créez votre espace, soumettez un fichier et suivez son parcours jusqu’au résultat.</p></div><UiButton :to="primaryTarget" size="large" icon="arrow">{{ isAuthenticated ? 'Accéder au dashboard' : 'Créer mon espace' }}</UiButton></section>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const { isAuthenticated } = useSession();
const primaryTarget = computed(() => isAuthenticated.value ? '/dashboard' : '/auth?mode=register');
const principles = [
  { number: '01', title: 'Une vision unifiée', text: 'Une seule interface relie les charges, les ressources et les résultats.', icon: 'overview' },
  { number: '02', title: 'Une distribution explicable', text: 'Chaque fragment garde son état, son rôle et sa trace d’exécution.', icon: 'layers' },
  { number: '03', title: 'Une confiance vérifiable', text: 'Les preuves et empreintes accompagnent le résultat final.', icon: 'shield' },
];
useSeoMeta({ title: 'Silicium — Votre réseau, une seule puissance', description: 'Distribuez des calculs sur un réseau coordonné et suivez chaque exécution de bout en bout.' });
</script>

<style scoped>
.hero{display:grid;min-height:calc(100vh - 4.75rem);grid-template-columns:minmax(360px,.82fr) minmax(520px,1.18fr);align-items:center;gap:clamp(2rem,5vw,5rem);padding-top:4.2rem;padding-bottom:4.2rem}.hero__eyebrow{display:flex;align-items:center;gap:.55rem;color:var(--mint-700);font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase}.hero__eyebrow span{width:.48rem;height:.48rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 5px var(--mint-100)}.hero h1{margin:1.25rem 0 0;font-size:clamp(3.5rem,6.5vw,6.7rem);font-weight:800;line-height:.91;letter-spacing:-.075em}.hero h1 em{color:var(--ink-500);font-style:normal;font-weight:600}.hero__copy>p{max-width:590px;margin:1.65rem 0 0;color:var(--ink-600);font-size:clamp(.92rem,1.3vw,1.08rem);line-height:1.75}.hero__actions{display:flex;flex-wrap:wrap;gap:.7rem;margin-top:2rem}.hero__proof{display:flex;flex-wrap:wrap;gap:1rem;margin-top:2.2rem;color:var(--ink-500);font-size:.62rem;font-weight:650}.hero__proof span{display:flex;align-items:center;gap:.35rem}.hero__proof svg{width:.85rem;color:var(--mint-700)}
.principles{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--border);border-radius:var(--radius-xl);background:rgba(255,255,255,.8);box-shadow:var(--shadow-sm)}.principles article{padding:2rem;border-right:1px solid var(--border)}.principles article:last-child{border:0}.principles article>div{display:grid;width:2.75rem;height:2.75rem;place-items:center;border-radius:.8rem;background:var(--mint-100);color:var(--mint-700)}.principles article:nth-child(2)>div{background:var(--violet-100);color:var(--violet-600)}.principles svg{width:1.1rem}.principles .eyebrow{display:block;margin-top:2rem;color:var(--ink-400)}.principles h2{margin:.55rem 0;font-size:1rem;letter-spacing:-.03em}.principles p{margin:0;color:var(--ink-600);font-size:.73rem;line-height:1.7}
.flow-section{padding-top:7rem}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:3rem;margin-bottom:2rem}.section-heading h2,.feature h2,.final-cta h2{max-width:700px;margin:.7rem 0 0;font-size:clamp(2rem,4vw,3.5rem);line-height:1.04;letter-spacing:-.06em}.section-heading>p{max-width:390px;margin:0;color:var(--ink-600);font-size:.78rem;line-height:1.7}
.feature{display:grid;grid-template-columns:1.05fr .95fr;align-items:center;gap:clamp(2.5rem,7vw,7rem);padding-top:8rem}.feature__visual{padding:2rem;border:1px solid var(--border);border-radius:var(--radius-xl);background:linear-gradient(145deg,var(--mint-100),rgba(238,236,255,.65))}.feature__window{overflow:hidden;border:1px solid var(--border);border-radius:1rem;background:white;box-shadow:var(--shadow-md)}.feature__window header{display:flex;align-items:center;gap:.3rem;height:2.8rem;padding:0 .8rem;border-bottom:1px solid var(--border);background:var(--surface-soft)}.feature__window header>span{width:.4rem;height:.4rem;border-radius:50%;background:var(--ink-200)}.feature__window header strong{margin-left:.5rem;font-size:.56rem}.feature__window-body{display:grid;gap:.85rem;padding:1rem}.feature__line{display:flex;align-items:center;gap:.75rem}.feature__line>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.55rem;background:var(--mint-100);color:var(--mint-700)}.feature__line>span.violet{background:var(--violet-100);color:var(--violet-600)}.feature__line svg{width:.8rem}.feature__line strong,.feature__line small{display:block}.feature__line strong{font-size:.65rem}.feature__line small{margin-top:.2rem;color:var(--ink-500);font-size:.54rem}.feature__result{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.75rem;margin-top:.35rem;padding:1rem;border-radius:.75rem;background:var(--ink-950);color:white}.feature__result>svg{width:1.1rem;color:var(--mint-500)}.feature__result strong,.feature__result small{display:block}.feature__result strong{font-size:.66rem}.feature__result small{margin-top:.18rem;color:rgba(255,255,255,.45);font-size:.54rem}.feature__copy>p{margin:1.2rem 0;color:var(--ink-600);font-size:.82rem;line-height:1.8}.feature__copy ul{display:grid;gap:.7rem;margin:1.5rem 0 2rem;padding:0;list-style:none}.feature__copy li{display:flex;align-items:center;gap:.55rem;color:var(--ink-700);font-size:.74rem;font-weight:650}.feature__copy li svg{width:.9rem;color:var(--mint-700)}
.final-cta{display:flex;align-items:center;justify-content:space-between;gap:2rem;margin-top:8rem;padding:3rem;border-radius:var(--radius-xl);background:var(--ink-950);color:white;box-shadow:var(--shadow-md)}.final-cta .eyebrow{color:var(--mint-200)}.final-cta h2{font-size:clamp(2rem,4vw,3.3rem)}.final-cta p{margin:1rem 0 0;color:rgba(255,255,255,.5);font-size:.78rem}.final-cta :deep(.ui-button){background:white;color:var(--ink-950)}
@media(max-width:1080px){.hero{grid-template-columns:1fr;padding-top:4rem}.hero__copy{max-width:760px}.hero h1{font-size:clamp(3.5rem,10vw,6rem)}.hero :deep(.network-illustration){min-height:430px}.feature{gap:3rem}}
@media(max-width:760px){.hero{min-height:auto;padding-top:3rem}.hero h1{font-size:clamp(3rem,16vw,4.8rem)}.principles{grid-template-columns:1fr}.principles article{display:grid;grid-template-columns:3rem 1fr;column-gap:1rem;border-right:0;border-bottom:1px solid var(--border);padding:1.3rem}.principles .eyebrow{display:none}.principles h2{margin:.15rem 0}.principles p{grid-column:2}.section-heading,.final-cta{align-items:stretch;flex-direction:column}.flow-section,.feature{padding-top:5rem}.feature{grid-template-columns:1fr}.feature__copy{grid-row:1}.feature__visual{padding:1rem}.final-cta{margin-top:5rem;padding:2rem}.final-cta :deep(.ui-button){align-self:flex-start}}
</style>
