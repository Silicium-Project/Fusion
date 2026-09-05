<template>
  <div class="landing-shell min-h-screen overflow-hidden text-white">
    <a href="#contenu" class="skip-link">Aller au contenu</a>
    <div class="page-grid" aria-hidden="true"></div>
    <div class="ambient ambient-one" aria-hidden="true"></div>
    <div class="ambient ambient-two" aria-hidden="true"></div>

    <Header />

    <main id="contenu" class="relative z-10">
      <section class="mx-auto grid min-h-[92vh] max-w-7xl items-center gap-14 px-6 pb-20 pt-36 md:px-8 lg:grid-cols-[1.02fr_0.98fr] lg:pb-24 lg:pt-40">
        <div class="max-w-3xl">
          <div class="reveal flex items-center gap-3 text-xs font-bold uppercase tracking-[0.2em] text-white/55">
            <span class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2">
              <span class="h-1.5 w-1.5 rounded-full bg-[#71eed7]"></span>
              Calcul distribué
            </span>
            <span class="hidden text-white/30 sm:inline">Construit pour passer à l’échelle</span>
          </div>

          <h1 class="reveal reveal-delay-1 mt-7 text-[clamp(3.25rem,7vw,6.6rem)] font-extrabold leading-[0.92] tracking-[-0.065em]">
            Votre réseau.<br>
            <span class="hero-accent">Sa puissance réunie.</span>
          </h1>

          <p class="reveal reveal-delay-2 mt-7 max-w-2xl text-lg leading-8 text-white/60 md:text-xl md:leading-9">
            Silicium transforme vos machines disponibles en une infrastructure de calcul coordonnée. Soumettez un travail, distribuez-le sur le réseau et suivez chaque résultat depuis une interface unique.
          </p>

          <div class="reveal reveal-delay-3 mt-9 flex flex-col gap-3 sm:flex-row">
            <NuxtLink to="/auth?mode=register" class="primary-cta group">
              Commencer maintenant
              <svg viewBox="0 0 24 24" class="h-4 w-4 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M5 12h14m-6-6 6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </NuxtLink>
            <a href="#fonctionnement" class="secondary-cta">Voir comment ça fonctionne</a>
          </div>

          <div class="reveal reveal-delay-4 mt-10 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm text-white/42">
            <span v-for="benefit in benefits" :key="benefit" class="inline-flex items-center gap-2">
              <svg viewBox="0 0 20 20" class="h-4 w-4 text-[#71eed7]" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m4 10 4 4 8-8" stroke-linecap="round" stroke-linejoin="round" /></svg>
              {{ benefit }}
            </span>
          </div>
        </div>

        <div class="reveal reveal-delay-2 relative mx-auto w-full max-w-[610px] lg:mx-0">
          <div class="product-window">
            <div class="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
              <div class="flex items-center gap-2">
                <span class="h-2.5 w-2.5 rounded-full bg-white/15"></span>
                <span class="h-2.5 w-2.5 rounded-full bg-white/10"></span>
                <span class="h-2.5 w-2.5 rounded-full bg-white/10"></span>
              </div>
              <div class="rounded-full border border-white/[0.07] bg-black/20 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-white/35">silicium / workspace</div>
              <span class="flex items-center gap-2 text-[11px] font-semibold text-emerald-300/80"><span class="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Live</span>
            </div>

            <div class="grid gap-4 p-4 sm:p-5 md:grid-cols-[1.15fr_0.85fr]">
              <div class="space-y-4">
                <div class="panel-card p-5">
                  <div class="flex items-start justify-between gap-4">
                    <div><p class="ui-label">Travail actif</p><h2 class="mt-2 text-lg font-bold tracking-[-0.025em]">Raytracer · Scene 04</h2></div>
                    <span class="rounded-full bg-[#9b8cff]/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#b8afff]">En cours</span>
                  </div>
                  <div class="mt-8 flex items-end justify-between">
                    <div><span class="text-4xl font-extrabold tracking-[-0.05em]">78</span><span class="ml-1 text-lg text-white/35">%</span></div>
                    <span class="font-mono text-[11px] text-white/35">50 / 64 fragments</span>
                  </div>
                  <div class="mt-3 h-2 overflow-hidden rounded-full bg-white/[0.06]"><div class="progress-line h-full w-[78%] rounded-full"></div></div>
                </div>

                <div class="panel-card p-5">
                  <div class="flex items-center justify-between"><p class="ui-label">Activité réseau</p><span class="font-mono text-[10px] text-white/25">12:48:32 UTC</span></div>
                  <div class="mt-6 flex h-24 items-end gap-2" aria-hidden="true"><span v-for="height in activityBars" :key="height" class="activity-bar flex-1 rounded-t-sm" :style="{ height: `${height}%` }"></span></div>
                  <div class="mt-3 flex items-center justify-between text-[10px] text-white/25"><span>- 60 min</span><span>Maintenant</span></div>
                </div>
              </div>

              <div class="panel-card relative min-h-[320px] overflow-hidden p-5">
                <div class="flex items-center justify-between"><p class="ui-label">Nœuds disponibles</p><span class="text-xl font-bold tracking-[-0.04em]">08</span></div>
                <div class="network-map" aria-label="Aperçu du réseau de calcul">
                  <svg viewBox="0 0 220 240" class="absolute inset-0 h-full w-full" fill="none" aria-hidden="true">
                    <path d="M110 120 42 62M110 120l67-70M110 120l72 54M110 120l-61 61M42 62l71-30m64 18-64-18m69 142-5-124M49 181l-7-119m7 119 133-7" stroke="url(#lineGradient)" stroke-width="1" stroke-dasharray="3 5" />
                    <defs><linearGradient id="lineGradient"><stop stop-color="#9b8cff" stop-opacity=".65" /><stop offset="1" stop-color="#67e8d4" stop-opacity=".15" /></linearGradient></defs>
                  </svg>
                  <span class="network-node node-main"><i></i></span><span class="network-node node-a"></span><span class="network-node node-b"></span><span class="network-node node-c"></span><span class="network-node node-d"></span><span class="network-node node-e"></span>
                </div>
                <div class="absolute inset-x-5 bottom-5 grid grid-cols-2 gap-2">
                  <div class="rounded-xl bg-white/[0.035] p-3"><p class="text-[10px] text-white/30">Latence</p><p class="mt-1 font-mono text-sm font-semibold text-white/75">24 ms</p></div>
                  <div class="rounded-xl bg-white/[0.035] p-3"><p class="text-[10px] text-white/30">Actifs</p><p class="mt-1 font-mono text-sm font-semibold text-white/75">6 / 8</p></div>
                </div>
              </div>
            </div>
          </div>
          <div class="floating-chip -left-4 top-24 hidden lg:flex">
            <span class="grid h-8 w-8 place-items-center rounded-lg bg-emerald-400/10 text-emerald-300"><svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m4 10 4 4 8-8" stroke-linecap="round" stroke-linejoin="round" /></svg></span>
            <span><b class="block text-xs text-white/85">Fragment vérifié</b><small class="text-[10px] text-white/35">Node eu-west-04</small></span>
          </div>
        </div>
      </section>

      <section class="border-y border-white/[0.07] bg-white/[0.018]">
        <div class="mx-auto grid max-w-7xl divide-y divide-white/[0.07] px-6 md:grid-cols-3 md:divide-x md:divide-y-0 md:px-8">
          <div class="status-summary"><span class="status-icon status-icon-up"></span><div><p class="summary-label">Orchestration</p><p class="summary-value">Un point de contrôle</p></div></div>
          <div class="status-summary md:pl-8"><span class="status-icon status-icon-up"></span><div><p class="summary-label">Distribution</p><p class="summary-value">Calcul par fragments</p></div></div>
          <div class="status-summary md:pl-8"><span class="status-icon status-icon-up"></span><div><p class="summary-label">Observation</p><p class="summary-value">Progression en direct</p></div></div>
        </div>
      </section>

      <section id="produit" class="section-space mx-auto max-w-7xl px-6 md:px-8">
        <div class="max-w-2xl">
          <p class="section-kicker">Une plateforme, tout le flux</p>
          <h2 class="section-title">Du fichier source au résultat, sans angle mort.</h2>
          <p class="section-copy">Silicium réunit l’orchestration, l’observation et la distribution dans une expérience cohérente.</p>
        </div>
        <div class="mt-14 grid gap-4 md:grid-cols-3">
          <article v-for="feature in features" :key="feature.title" class="feature-card group">
            <div class="feature-number">0{{ feature.index }}</div>
            <div class="feature-icon" v-html="feature.icon"></div>
            <h3 class="mt-10 text-xl font-bold tracking-[-0.025em]">{{ feature.title }}</h3>
            <p class="mt-3 text-sm leading-6 text-white/48">{{ feature.description }}</p>
            <div class="mt-8 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-white/35 transition group-hover:text-[#8ef3df]">{{ feature.detail }}<span aria-hidden="true">→</span></div>
          </article>
        </div>
      </section>

      <section id="fonctionnement" class="section-space border-y border-white/[0.07] bg-white/[0.018]">
        <div class="mx-auto grid max-w-7xl gap-14 px-6 md:px-8 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <div class="lg:sticky lg:top-28">
            <p class="section-kicker">Simple par conception</p><h2 class="section-title">Trois étapes. Un réseau prêt à calculer.</h2>
            <p class="section-copy">L’interface garde la complexité technique en arrière-plan et montre seulement ce qui vous aide à décider.</p>
            <a :href="nodeAppWindowsUrl" class="mt-8 inline-flex items-center gap-2 text-sm font-bold text-[#8ef3df] transition hover:text-white" download>
              Télécharger le nœud Windows
              <svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M10 3v10m-4-4 4 4 4-4M4 17h12" stroke-linecap="round" stroke-linejoin="round" /></svg>
            </a>
          </div>
          <ol class="space-y-3">
            <li v-for="step in steps" :key="step.number" class="process-step">
              <div class="step-number">{{ step.number }}</div>
              <div><h3 class="text-lg font-bold tracking-[-0.02em]">{{ step.title }}</h3><p class="mt-2 max-w-xl text-sm leading-6 text-white/45">{{ step.description }}</p></div>
              <span class="ml-auto hidden font-mono text-[10px] uppercase tracking-[0.14em] text-white/20 sm:block">{{ step.meta }}</span>
            </li>
          </ol>
        </div>
      </section>

      <section id="statut" class="section-space mx-auto max-w-7xl px-6 md:px-8">
        <div class="grid gap-12 lg:grid-cols-[0.72fr_1.28fr] lg:items-start">
          <div>
            <p class="section-kicker">Infrastructure maîtrisée</p><h2 class="section-title">La complexité technique reste à sa place.</h2>
            <p class="section-copy">Chaque composant possède un rôle clair. Une page dédiée rassemble l’état des services, les versions publiées et les téléchargements disponibles.</p>
            <NuxtLink to="/service" class="secondary-cta mt-8">Consulter l’état des services <span aria-hidden="true">→</span></NuxtLink>
          </div>

          <div class="overflow-hidden rounded-[1.75rem] border border-white/[0.09] bg-[#0d1017] shadow-[0_30px_80px_rgba(0,0,0,0.25)]">
            <div class="flex items-center justify-between border-b border-white/[0.07] px-5 py-4 sm:px-6">
              <div class="flex items-center gap-3"><span class="h-2 w-2 rounded-sm bg-[#9b8cff]"></span><span class="text-sm font-bold">Architecture Silicium</span></div>
              <span class="font-mono text-[10px] uppercase tracking-wider text-white/25">3 composants</span>
            </div>
            <div class="divide-y divide-white/[0.06]">
              <article v-for="layer in architectureLayers" :key="layer.name" class="grid gap-3 px-5 py-5 sm:grid-cols-[1fr_auto] sm:items-center sm:px-6">
                <div><h3 class="text-sm font-bold text-white/85">{{ layer.name }}</h3><p class="mt-1.5 text-xs leading-5 text-white/38">{{ layer.description }}</p></div>
                <span class="rounded-lg bg-white/[0.045] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider text-white/30">{{ layer.role }}</span>
              </article>
            </div>
            <div class="border-t border-white/[0.07] bg-black/15 px-5 py-4 sm:px-6">
              <NuxtLink to="/service" class="flex items-center justify-between text-xs font-bold text-[#8ef3df] transition hover:text-white"><span>Ouvrir le centre de statut</span><span aria-hidden="true">↗</span></NuxtLink>
            </div>
          </div>
        </div>
      </section>

      <section class="mx-auto max-w-7xl px-6 pb-20 md:px-8 md:pb-28">
        <div class="cta-panel relative overflow-hidden rounded-[2rem] border border-white/10 px-6 py-12 sm:px-10 md:py-16">
          <div class="relative z-10 max-w-2xl">
            <p class="section-kicker !text-[#a9ffe9]">Prêt à lancer le premier calcul ?</p>
            <h2 class="mt-4 text-3xl font-extrabold tracking-[-0.045em] sm:text-5xl">Branchez vos machines.<br>Silicium orchestre le reste.</h2>
            <div class="mt-8 flex flex-col gap-3 sm:flex-row"><NuxtLink to="/auth?mode=register" class="primary-cta">Créer un espace</NuxtLink><a :href="nodeAppWindowsUrl" class="secondary-cta" download>Télécharger le nœud</a></div>
          </div>
          <div class="cta-orbit" aria-hidden="true"><span></span><span></span><span></span></div>
        </div>
      </section>
    </main>

    <footer class="relative z-10 border-t border-white/[0.07]">
      <div class="mx-auto flex max-w-7xl flex-col gap-5 px-6 py-8 text-xs text-white/35 sm:flex-row sm:items-center sm:justify-between md:px-8">
        <div class="flex items-center gap-3"><span class="h-2 w-2 rounded-sm bg-[#9b8cff]"></span><span class="font-bold text-white/60">Silicium</span><span>Réseau de calcul distribué</span></div>
        <div class="flex items-center gap-5"><NuxtLink to="/service" class="transition hover:text-white">Statut</NuxtLink><NuxtLink to="/auth" class="transition hover:text-white">Connexion</NuxtLink><span>© {{ currentYear }}</span></div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import Header from '../components/Header.vue';

const { public: publicConfig } = useRuntimeConfig();
const nodeAppWindowsUrl = publicConfig.nodeAppWindowsUrl;
const currentYear = new Date().getFullYear();
const activityBars = [34, 48, 42, 66, 55, 76, 61, 83, 72, 92, 68, 86];
const benefits = ['Déploiement autonome', 'Suivi en temps réel', 'Contrôle centralisé'];

const features = [
  { index: 1, title: 'Orchestrez vos calculs', description: 'Déposez une tâche et configurez ses paramètres depuis un parcours guidé, sans gérer chaque machine individuellement.', detail: 'Soumission unifiée', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 4h14v16H5zM8 8h8M8 12h5M8 16h3" stroke-linecap="round" stroke-linejoin="round"/></svg>' },
  { index: 2, title: 'Distribuez intelligemment', description: 'Le réseau découpe le travail, assigne les fragments disponibles et coordonne les nœuds connectés.', detail: 'Réseau coordonné', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="m10.8 7.2-4.6 8.5m7-8.5 4.6 8.5M7.5 18h9"/></svg>' },
  { index: 3, title: 'Observez chaque étape', description: 'Suivez l’avancement, les nœuds et les résultats depuis un tableau de bord pensé pour agir rapidement.', detail: 'Visibilité en direct', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 19V9m5 10V5m5 14v-7m5 7V3" stroke-linecap="round"/><path d="M3 19.5h18"/></svg>' },
];

const steps = [
  { number: '01', title: 'Connectez les ressources', description: 'Installez le nœud Silicium sur les machines que vous souhaitez intégrer au réseau.', meta: 'Node app' },
  { number: '02', title: 'Soumettez une tâche', description: 'Choisissez le workload, la priorité et les fichiers nécessaires depuis votre espace.', meta: 'Dashboard' },
  { number: '03', title: 'Suivez et récupérez', description: 'Visualisez la progression des fragments, puis téléchargez le résultat lorsqu’il est validé.', meta: 'Result' },
];

const architectureLayers = [
  { name: 'Interface web', description: 'Comptes, soumission des tâches et visualisation des résultats.', role: 'Piloter' },
  { name: 'Backend API', description: 'Orchestration des travaux et coordination avec le réseau.', role: 'Coordonner' },
  { name: 'Réseau de nœuds', description: 'Exécution distribuée et remontée de la progression.', role: 'Calculer' },
];

useHead({ title: 'Silicium — Le calcul distribué, simplement', meta: [{ name: 'description', content: 'Silicium coordonne vos machines, distribue vos calculs et centralise le suivi de chaque résultat.' }] });

</script>

<style scoped>
.landing-shell { background: #080a0f; }
.page-grid { position: absolute; inset: 0 0 auto; height: 58rem; opacity: .38; background-image: linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px); background-size: 56px 56px; mask-image: linear-gradient(to bottom, black 0%, transparent 88%); }
.ambient { position: absolute; border-radius: 999px; filter: blur(110px); pointer-events: none; }.ambient-one { width: 28rem; height: 28rem; right: 4%; top: 7rem; background: rgba(120,99,255,.14); }.ambient-two { width: 24rem; height: 24rem; left: -10rem; top: 38rem; background: rgba(78,231,207,.07); }
.hero-accent { color: transparent; background: linear-gradient(105deg, #fff 2%, #aaa0ff 46%, #70ead7 96%); background-clip: text; -webkit-background-clip: text; }
.primary-cta,.secondary-cta { display:inline-flex;min-height:3.25rem;align-items:center;justify-content:center;gap:.65rem;border-radius:.9rem;padding:.85rem 1.25rem;font-size:.875rem;font-weight:750;transition:transform 180ms ease,background-color 180ms ease,border-color 180ms ease,color 180ms ease }.primary-cta{background:#f4f5f7;color:#080a0f;box-shadow:0 10px 35px rgba(0,0,0,.24)}.primary-cta:hover{background:#d9ff9d;transform:translateY(-2px)}.secondary-cta{border:1px solid rgba(255,255,255,.11);background:rgba(255,255,255,.035);color:rgba(255,255,255,.7)}.secondary-cta:hover{border-color:rgba(255,255,255,.22);color:#fff;background:rgba(255,255,255,.065)}
.product-window{position:relative;overflow:hidden;border:1px solid rgba(255,255,255,.1);border-radius:1.75rem;background:linear-gradient(145deg,rgba(18,21,31,.96),rgba(9,11,17,.98));box-shadow:0 50px 120px rgba(0,0,0,.48),inset 0 1px 0 rgba(255,255,255,.05)}.product-window::after{content:'';position:absolute;inset:0;pointer-events:none;background:linear-gradient(115deg,rgba(255,255,255,.055),transparent 28%)}.panel-card{border:1px solid rgba(255,255,255,.065);border-radius:1.1rem;background:rgba(255,255,255,.025)}.ui-label{font-size:.625rem;font-weight:750;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.28)}.progress-line{background:linear-gradient(90deg,#8574ff,#68e8d4);box-shadow:0 0 18px rgba(104,232,212,.3)}.activity-bar{min-width:4px;background:linear-gradient(to top,rgba(133,116,255,.12),rgba(133,116,255,.72))}
.network-map{position:relative;height:14.5rem}.network-node{position:absolute;width:.75rem;height:.75rem;border:2px solid #1a1e2b;border-radius:999px;background:#66dec9;box-shadow:0 0 0 3px rgba(102,222,201,.1),0 0 16px rgba(102,222,201,.35)}.network-node::after{content:'';position:absolute;inset:-.5rem}.node-main{width:1.2rem;height:1.2rem;left:calc(50% - .6rem);top:calc(50% - .6rem);background:#9b8cff;box-shadow:0 0 0 5px rgba(155,140,255,.12),0 0 24px rgba(155,140,255,.55)}.node-main i{position:absolute;inset:-.55rem;border:1px solid rgba(155,140,255,.32);border-radius:999px;animation:node-pulse 2.4s ease-out infinite}.node-a{left:15%;top:18%}.node-b{right:14%;top:13%}.node-c{right:12%;top:69%}.node-d{left:18%;top:72%}.node-e{left:48%;top:4%}.floating-chip{position:absolute;align-items:center;gap:.7rem;border:1px solid rgba(255,255,255,.1);border-radius:.85rem;background:rgba(12,15,22,.9);padding:.65rem .8rem;box-shadow:0 18px 45px rgba(0,0,0,.32);backdrop-filter:blur(14px)}
.status-summary{display:flex;min-height:6.5rem;align-items:center;gap:1rem}.status-icon{width:.55rem;height:.55rem;flex:none;border-radius:999px}.status-icon-up{background:#41d7a2;box-shadow:0 0 0 5px rgba(65,215,162,.08)}.status-icon-down{background:#fb7185;box-shadow:0 0 0 5px rgba(251,113,133,.08)}.status-icon-loading{background:#fcd34d;box-shadow:0 0 0 5px rgba(252,211,77,.08);animation:soft-pulse 1.4s ease-in-out infinite}.summary-label{font-size:.625rem;font-weight:750;letter-spacing:.15em;text-transform:uppercase;color:rgba(255,255,255,.28)}.summary-value{margin-top:.3rem;font-size:.875rem;font-weight:700;color:rgba(255,255,255,.72)}
.section-space{padding-top:7rem;padding-bottom:7rem;scroll-margin-top:5rem}.section-kicker{font-size:.68rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:#9d91ff}.section-title{margin-top:1rem;font-size:clamp(2.35rem,5vw,4rem);font-weight:800;line-height:1.02;letter-spacing:-.052em}.section-copy{margin-top:1.3rem;max-width:38rem;font-size:1rem;line-height:1.8;color:rgba(255,255,255,.45)}
.feature-card{position:relative;min-height:23rem;overflow:hidden;border:1px solid rgba(255,255,255,.075);border-radius:1.5rem;background:rgba(255,255,255,.022);padding:1.6rem;transition:transform 220ms ease,border-color 220ms ease,background-color 220ms ease}.feature-card:hover{transform:translateY(-5px);border-color:rgba(157,145,255,.3);background:rgba(255,255,255,.035)}.feature-number{position:absolute;right:1.35rem;top:1.1rem;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.65rem;color:rgba(255,255,255,.18)}.feature-icon{display:grid;width:3.25rem;height:3.25rem;place-items:center;border:1px solid rgba(157,145,255,.2);border-radius:1rem;background:rgba(157,145,255,.08);color:#afa5ff}.feature-icon :deep(svg){width:1.45rem;height:1.45rem}
.process-step{display:flex;align-items:flex-start;gap:1.2rem;border:1px solid rgba(255,255,255,.07);border-radius:1.25rem;background:rgba(8,10,15,.55);padding:1.5rem;transition:border-color 180ms ease,transform 180ms ease}.process-step:hover{border-color:rgba(113,238,215,.22);transform:translateX(4px)}.step-number{display:grid;width:2.3rem;height:2.3rem;flex:none;place-items:center;border-radius:.75rem;background:rgba(113,238,215,.08);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.65rem;font-weight:700;color:#8ef3df}.status-pill{border-radius:999px;padding:.25rem .55rem;font-size:.58rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase}.release-row{display:flex;align-items:center;justify-content:space-between;border:1px solid rgba(255,255,255,.06);border-radius:.9rem;padding:.8rem;transition:border-color 160ms ease,background-color 160ms ease}.release-row:hover{border-color:rgba(255,255,255,.13);background:rgba(255,255,255,.025)}
.cta-panel{background:radial-gradient(circle at 78% 45%,rgba(113,238,215,.16),transparent 32%),linear-gradient(135deg,rgba(127,108,255,.17),rgba(255,255,255,.025) 46%,rgba(113,238,215,.07))}.cta-orbit{position:absolute;width:27rem;height:27rem;right:-5rem;top:-6rem;border:1px solid rgba(255,255,255,.06);border-radius:50%}.cta-orbit::before,.cta-orbit::after{content:'';position:absolute;border:1px solid rgba(255,255,255,.06);border-radius:50%}.cta-orbit::before{inset:3.5rem}.cta-orbit::after{inset:7rem}.cta-orbit span{position:absolute;width:.7rem;height:.7rem;border-radius:50%;background:#87efdc;box-shadow:0 0 18px rgba(135,239,220,.65)}.cta-orbit span:first-child{left:2.6rem;top:7rem}.cta-orbit span:nth-child(2){right:5.2rem;bottom:2.8rem;background:#a499ff}.cta-orbit span:nth-child(3){left:50%;top:50%}
.reveal{animation:reveal-up .65s both cubic-bezier(.2,.7,.2,1)}.reveal-delay-1{animation-delay:.08s}.reveal-delay-2{animation-delay:.16s}.reveal-delay-3{animation-delay:.24s}.reveal-delay-4{animation-delay:.32s}@keyframes reveal-up{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}@keyframes node-pulse{0%{transform:scale(.7);opacity:.8}80%,100%{transform:scale(1.7);opacity:0}}@keyframes soft-pulse{50%{opacity:.45}}
@media(max-width:767px){.section-space{padding-top:5.5rem;padding-bottom:5.5rem}.feature-card{min-height:auto}.cta-orbit{opacity:.45;right:-15rem}}@media(prefers-reduced-motion:reduce){.reveal,.node-main i,.status-icon-loading{animation:none}.primary-cta:hover,.feature-card:hover,.process-step:hover{transform:none}}
</style>
