<template>
  <div class="home-page marketing-page">
    <section class="home-hero marketing-container">
      <div v-reveal="'left'" class="home-hero__copy">
        <span class="marketing-kicker">Calcul distribué, simplement</span>
        <h1 class="marketing-title">Ne soyez plus limité<br><em>par votre matériel.</em></h1>
        <p class="marketing-lede">Envoyez votre projet. Silicium mobilise plusieurs machines et vous rend un résultat contrôlé.</p>
        <div class="marketing-action-row">
          <UiButton :to="primaryTarget" size="large" icon="arrow">{{ isAuthenticated ? 'Ouvrir mon espace' : 'Commencer maintenant' }}</UiButton>
          <UiButton to="/service" variant="secondary" size="large">Voir comment ça fonctionne</UiButton>
        </div>
        <div class="home-hero__meta" aria-label="Engagements Silicium">
          <span><i>01</i>Un seul envoi</span>
          <span><i>02</i>Plusieurs machines</span>
          <span><i>03</i>Un résultat contrôlé</span>
        </div>
      </div>
      <GlassNetworkPanel v-reveal="'right'" />
    </section>

    <section class="home-signal marketing-container marketing-glass" aria-label="Principes de Silicium">
      <div class="home-signal__lead"><span class="marketing-kicker">Le principe</span><strong>Votre projet ne dépend plus d’une seule machine.</strong></div>
      <div class="home-signal__point"><span>01</span><p>Envoyez votre projet une seule fois.</p></div>
      <div class="home-signal__point"><span>02</span><p>Le réseau trouve les machines disponibles.</p></div>
      <div class="home-signal__point"><span>03</span><p>Récupérez un résultat vérifié.</p></div>
    </section>

    <section class="home-process marketing-container marketing-section">
      <div v-reveal class="marketing-section-heading">
        <div><span class="marketing-kicker">Comment ça marche</span><h2>Vous envoyez.<br>Le réseau travaille.</h2></div>
        <p>Silicium répartit automatiquement votre projet, contrôle les résultats et vous rend une réponse claire.</p>
      </div>
      <ProcessFlow />
    </section>

    <section class="home-chain marketing-container marketing-section--tight">
      <div v-reveal="'left'" class="home-chain__copy">
        <span class="marketing-kicker">Blockchain et paiements</span>
        <h2>Votre résultat, avec<br><em>une preuve visible.</em></h2>
        <p>La blockchain garde une trace des paiements et des contrôles liés à votre projet. Vos fichiers restent dans le réseau.</p>
        <ul><li><UiIcon name="shield" />Une trace du projet</li><li><UiIcon name="wallet" />Des paiements clairs</li><li><UiIcon name="check" />Vos clés restent chez vous</li></ul>
        <UiButton to="/blockchain" variant="secondary" icon="arrow">Voir comment ça marche</UiButton>
      </div>
      <OnchainLedger v-reveal="'right'" compact :status="status?.blockchain" />
    </section>

    <section class="home-receipt marketing-container marketing-section--tight">
      <div v-reveal="'left'" class="home-receipt__visual marketing-glass">
        <header class="home-receipt__bar"><span><i></i><i></i><i></i></span><strong>PROJET / RÉSULTAT</strong><small>EN DIRECT</small></header>
        <div class="home-receipt__body">
          <div class="home-receipt__headline"><div><span class="marketing-kicker">Résultat vérifiable</span><strong>Résultat disponible</strong></div><span class="home-receipt__check"><UiIcon name="check" /></span></div>
          <div class="home-receipt__progress"><span>Parties vérifiées</span><strong>64 / 64</strong><div><i></i></div></div>
          <div class="home-receipt__rows">
            <div><span><UiIcon name="layers" /></span><p><strong>Calcul terminé</strong><small>5 machines · contrôles terminés</small></p><b>08:42</b></div>
            <div><span><UiIcon name="shield" /></span><p><strong>Résultat contrôlé</strong><small>Origine du résultat conservée</small></p><b>08:43</b></div>
            <div><span><UiIcon name="result" /></span><p><strong>Image prête</strong><small>PNG · 4K · 18.4 MB</small></p><b class="home-receipt__valid">VÉRIFIÉ</b></div>
          </div>
        </div>
      </div>
      <div v-reveal="'right'" class="home-receipt__copy">
        <span class="marketing-kicker">Suivi en clair</span>
        <h2>Vous voyez ce qui<br><em>se passe.</em></h2>
        <p>L’avancement, le résultat et les informations utiles sont réunis au même endroit.</p>
        <ul><li><UiIcon name="check" />Une vue claire de l’avancement</li><li><UiIcon name="check" />Les informations utiles au bon moment</li><li><UiIcon name="check" />Un résultat dont l’origine est visible</li></ul>
        <UiButton to="/about" variant="secondary" icon="arrow">Découvrir notre approche</UiButton>
      </div>
    </section>

    <section v-reveal class="home-cta marketing-container marketing-glass">
      <div><span class="marketing-kicker">Prêt à essayer ?</span><h2>Faites avancer vos projets<br><em>avec le réseau.</em></h2><p>Envoyez votre projet et laissez plusieurs machines se partager le travail.</p></div>
      <UiButton :to="primaryTarget" size="large" icon="arrow">{{ isAuthenticated ? 'Accéder à mon espace' : 'Commencer maintenant' }}</UiButton>
    </section>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'public' });
const { isAuthenticated } = useSession();
const { status, refresh } = useSystemStatus();
const primaryTarget = computed(() => isAuthenticated.value ? '/dashboard' : '/auth?mode=register');
onMounted(() => { refresh(); });
useSeoMeta({ title: 'Silicium — Plus de puissance pour vos projets', description: 'Silicium répartit vos calculs sur un réseau de machines et vous rend des résultats vérifiés.' });
</script>

<style scoped>
.home-hero{display:grid;grid-template-columns:minmax(0,1.06fr) minmax(26rem,.94fr);align-items:center;gap:clamp(2.5rem,5vw,5rem);min-height:min(720px,calc(100svh - 5rem));padding-block:clamp(3.5rem,7vw,6rem)}
.home-hero__copy{min-width:0}.home-hero__copy .marketing-title{max-width:700px;font-size:clamp(3rem,4.7vw,5.2rem)}.home-hero__meta{display:flex;flex-wrap:wrap;gap:.95rem 1.5rem;margin-top:1.8rem;color:var(--ink-600);font-size:.72rem;font-weight:680}.home-hero__meta span{display:inline-flex;align-items:center;gap:.45rem}.home-hero__meta i{color:var(--ink-400);font-family:var(--font-mono);font-size:.58rem;font-style:normal;font-weight:500}
.home-signal{display:grid;grid-template-columns:1.25fr repeat(3,1fr);gap:0;border-radius:1.6rem;background:linear-gradient(105deg,rgba(255,255,255,.8),rgba(224,248,243,.4));}.home-signal__lead,.home-signal__point{min-width:0;padding:1.65rem;border-right:1px solid var(--border)}.home-signal__point:last-child{border:0}.home-signal__lead strong{display:block;max-width:18rem;margin-top:.65rem;color:var(--ink-900);font-size:1.05rem;line-height:1.25;letter-spacing:-.035em}.home-signal__point span{color:var(--mint-700);font-family:var(--font-mono);font-size:.58rem}.home-signal__point p{margin:.7rem 0 0;color:var(--ink-700);font-size:.78rem;line-height:1.65}
.home-process{padding-top:clamp(5rem,9vw,8rem)}
.home-chain{display:grid;grid-template-columns:minmax(0,.9fr) minmax(27rem,1.1fr);align-items:center;gap:clamp(3rem,8vw,8rem);padding-top:clamp(4rem,7vw,7rem)}.home-chain__copy h2{margin:.95rem 0 0;color:var(--ink-900);font-size:clamp(2.4rem,4.7vw,4.6rem);font-weight:640;line-height:.98;letter-spacing:-.067em}.home-chain__copy h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.home-chain__copy>p{max-width:520px;margin:1.35rem 0 0;color:var(--ink-700);font-size:1rem;line-height:1.78}.home-chain__copy ul{display:grid;gap:.7rem;margin:1.4rem 0 1.8rem;padding:0;list-style:none}.home-chain__copy li{display:flex;align-items:center;gap:.55rem;color:var(--ink-700);font-size:.8rem;font-weight:700}.home-chain__copy li svg{width:.9rem;color:var(--mint-700)}
.home-receipt{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);align-items:center;gap:clamp(3rem,8vw,8rem)}.home-receipt__visual{overflow:hidden;border-radius:1.8rem;background:linear-gradient(145deg,rgba(255,255,255,.8),rgba(227,249,245,.5) 55%,rgba(239,237,255,.44))}.home-receipt__bar{display:flex;align-items:center;gap:.75rem;padding:1rem 1.2rem;border-bottom:1px solid var(--border);color:var(--ink-500)}.home-receipt__bar>span{display:flex;gap:.28rem}.home-receipt__bar>span i{width:.38rem;height:.38rem;border-radius:50%;background:var(--ink-300)}.home-receipt__bar>span i:first-child{background:var(--mint-500)}.home-receipt__bar strong{font-family:var(--font-mono);font-size:.54rem;font-weight:500;letter-spacing:.04em}.home-receipt__bar small{margin-left:auto;color:var(--mint-700);font-family:var(--font-mono);font-size:.53rem}.home-receipt__body{padding:1.5rem}.home-receipt__headline{display:flex;align-items:center;justify-content:space-between;gap:1rem}.home-receipt__headline .marketing-kicker{font-size:.58rem}.home-receipt__headline strong{display:block;margin-top:.48rem;color:var(--ink-900);font-size:1.35rem;letter-spacing:-.045em}.home-receipt__check{display:grid;width:2.65rem;height:2.65rem;place-items:center;border:1px solid rgba(18,191,174,.2);border-radius:50%;background:var(--mint-100);color:var(--mint-700)}.home-receipt__check svg{width:1.05rem}.home-receipt__progress{display:grid;grid-template-columns:1fr auto;gap:.45rem 1rem;margin:1.8rem 0 1.35rem;color:var(--ink-600);font-size:.68rem}.home-receipt__progress strong{color:var(--ink-900);font-family:var(--font-mono);font-size:.62rem;font-weight:600}.home-receipt__progress>div{grid-column:1/-1;overflow:hidden;height:.42rem;border-radius:99px;background:rgba(21,40,61,.1)}.home-receipt__progress>div i{display:block;width:100%;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--mint-500),var(--violet-500));transform-origin:left;animation:receipt-progress 1.8s var(--ease-out) both}.home-receipt__rows{display:grid;gap:.65rem}.home-receipt__rows>div{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.75rem;padding:.72rem;border:1px solid rgba(255,255,255,.75);border-radius:.85rem;background:rgba(255,255,255,.55)}.home-receipt__rows>div>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.6rem;background:rgba(225,248,243,.8);color:var(--mint-700)}.home-receipt__rows>div:nth-child(2)>span{background:var(--violet-100);color:var(--violet-600)}.home-receipt__rows svg{width:.85rem}.home-receipt__rows p,.home-receipt__rows strong,.home-receipt__rows small{display:block}.home-receipt__rows p{margin:0}.home-receipt__rows strong{color:var(--ink-900);font-size:.69rem}.home-receipt__rows small{margin-top:.22rem;color:var(--ink-600);font-size:.58rem}.home-receipt__rows b{color:var(--ink-500);font-family:var(--font-mono);font-size:.55rem;font-weight:500}.home-receipt__rows b.home-receipt__valid{color:var(--mint-700);font-weight:700}
.home-receipt__copy h2{margin:.95rem 0 0;color:var(--ink-900);font-size:clamp(2.35rem,4.5vw,4.2rem);font-weight:640;line-height:.98;letter-spacing:-.065em}.home-receipt__copy h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.home-receipt__copy>p{max-width:510px;margin:1.45rem 0 0;color:var(--ink-700);font-size:1.05rem;line-height:1.8}.home-receipt__copy ul{display:grid;gap:.75rem;margin:1.6rem 0 2rem;padding:0;list-style:none}.home-receipt__copy li{display:flex;align-items:center;gap:.55rem;color:var(--ink-700);font-size:.84rem;font-weight:680}.home-receipt__copy li svg{width:.92rem;color:var(--mint-700)}
.home-cta{display:flex;align-items:center;justify-content:space-between;gap:2rem;margin-top:clamp(4rem,8vw,8rem);padding:clamp(1.75rem,4vw,3.4rem);border-radius:1.8rem;background:linear-gradient(120deg,rgba(255,255,255,.82),rgba(225,248,243,.64) 55%,rgba(238,236,255,.58));}.home-cta h2{margin:.9rem 0 0;color:var(--ink-900);font-size:clamp(1.9rem,3.7vw,3.4rem);font-weight:640;line-height:1.02;letter-spacing:-.06em}.home-cta h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.home-cta p{max-width:520px;margin:.9rem 0 0;color:var(--ink-700);font-size:.95rem;line-height:1.7}.home-cta :deep(.ui-button){flex:none}
@keyframes receipt-progress{from{transform:scaleX(0)}}
@media(max-width:1050px){.home-hero{grid-template-columns:1fr;min-height:auto;gap:3rem}.home-hero__copy{max-width:780px}.home-hero :deep(.network-panel){max-width:780px;margin-inline:auto}.home-signal{grid-template-columns:1.2fr 1fr 1fr}.home-signal__point:last-child{display:none}.home-chain{grid-template-columns:1fr;gap:3rem}.home-chain__copy{max-width:780px}.home-chain :deep(.onchain-ledger){max-width:780px;width:100%;margin-inline:auto}.home-receipt{gap:3rem}}
@media(max-width:760px){.home-hero{padding-block:3.5rem 4.5rem}.home-signal{grid-template-columns:1fr 1fr}.home-signal__lead{grid-column:1/-1;border-right:0;border-bottom:1px solid var(--border)}.home-signal__point:nth-child(3){border-right:0}.home-signal__point:last-child{display:block;grid-column:1/-1;border-top:1px solid var(--border);border-right:0}.home-receipt{grid-template-columns:1fr}.home-receipt__copy{order:-1}.home-cta{align-items:flex-start;flex-direction:column}.home-cta :deep(.ui-button){width:100%}}
@media(max-width:520px){.home-hero{padding-block:3rem 3.5rem}.home-hero__meta{display:grid;gap:.7rem;margin-top:1.6rem}.home-signal{grid-template-columns:1fr;border-radius:1.25rem}.home-signal__lead,.home-signal__point{grid-column:auto;border-right:0;border-bottom:1px solid var(--border)}.home-signal__point:last-child{grid-column:auto;border-top:0;border-bottom:0}.home-receipt__body{padding:1.1rem}.home-receipt__rows>div{grid-template-columns:auto 1fr}.home-receipt__rows b{grid-column:2}.home-receipt__rows b.home-receipt__valid{justify-self:start}.home-cta{border-radius:1.35rem}}
</style>
