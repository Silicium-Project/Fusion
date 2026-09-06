<template>
  <div class="network-illustration" aria-label="Schéma du flux Silicium : une tâche est découpée, distribuée aux nœuds, vérifiée puis réassemblée">
    <div class="network-illustration__grid" aria-hidden="true"></div>
    <svg class="network-illustration__paths" viewBox="0 0 760 470" preserveAspectRatio="none" aria-hidden="true">
      <path d="M95 235C170 235 185 235 255 235M355 235C425 235 430 105 515 105M355 235C425 235 430 195 515 195M355 235C425 235 430 285 515 285M355 235C425 235 430 375 515 375M605 105C660 105 660 235 700 235M605 195C650 195 660 235 700 235M605 285C650 285 660 235 700 235M605 375C660 375 660 235 700 235" />
    </svg>
    <div class="network-illustration__node network-illustration__node--input"><UiIcon name="upload"/><span>Entrée</span><small>scene.cfg</small></div>
    <div class="network-illustration__orchestrator"><span class="network-illustration__logo"><img src="/brand/silicium-logo.png" alt=""></span><strong>Orchestration</strong><small>Découpage & attribution</small><div class="network-illustration__fragments"><i v-for="n in 6" :key="n"></i></div></div>
    <div v-for="node in nodes" :key="node.label" class="network-illustration__node network-illustration__node--worker" :style="node.style"><UiIcon :name="node.icon"/><span>{{ node.label }}</span><small>{{ node.detail }}</small></div>
    <div class="network-illustration__node network-illustration__node--result"><UiIcon name="shield"/><span>Résultat</span><small>Vérifié</small></div>
    <div class="network-illustration__legend"><span><i class="mint"></i> Calcul</span><span><i class="violet"></i> Vérification</span><span><i class="ink"></i> Réassemblage</span></div>
  </div>
</template>

<script setup lang="ts">
const nodes = [
  { label: 'Compute · 01', detail: 'Fragment 12', icon: 'processor', style: { top: '12%', left: '67%' } },
  { label: 'Compute · 02', detail: 'Fragment 13', icon: 'processor', style: { top: '32%', left: '67%' } },
  { label: 'Verify · 01', detail: 'Preuve reçue', icon: 'shield', style: { top: '52%', left: '67%' } },
  { label: 'Storage · 01', detail: 'Résultat chiffré', icon: 'database', style: { top: '72%', left: '67%' } },
];
</script>

<style scoped>
.network-illustration{position:relative;min-height:470px;overflow:hidden;border:1px solid rgba(23,34,49,.11);border-radius:1.6rem;background:rgba(255,255,255,.82);box-shadow:var(--shadow-md)}.network-illustration__grid{position:absolute;inset:0;opacity:.55;background-image:linear-gradient(rgba(23,34,49,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(23,34,49,.045) 1px,transparent 1px);background-size:32px 32px;mask-image:radial-gradient(circle,#000 15%,transparent 76%)}
.network-illustration__paths{position:absolute;inset:0;width:100%;height:100%}.network-illustration__paths path{fill:none;stroke:rgba(13,149,136,.42);stroke-width:1.6;stroke-dasharray:5 5;animation:flow 18s linear infinite}@keyframes flow{to{stroke-dashoffset:-120}}
.network-illustration__node,.network-illustration__orchestrator{position:absolute;z-index:2;border:1px solid var(--border);background:rgba(255,255,255,.95);box-shadow:0 10px 28px rgba(17,27,42,.09)}.network-illustration__node{display:grid;width:112px;min-height:74px;place-items:center;border-radius:1rem;padding:.65rem}.network-illustration__node svg{width:1.1rem;color:var(--mint-700)}.network-illustration__node span{font-size:.64rem;font-weight:800}.network-illustration__node small{color:var(--ink-500);font-size:.53rem}.network-illustration__node--input{top:calc(50% - 38px);left:3%}.network-illustration__node--result{top:calc(50% - 38px);right:1.8%}.network-illustration__node--result svg{color:var(--violet-600)}
.network-illustration__orchestrator{top:calc(50% - 82px);left:34%;display:flex;width:152px;height:164px;align-items:center;justify-content:center;flex-direction:column;border-radius:1.35rem}.network-illustration__logo{display:grid;width:3.5rem;height:3.5rem;place-items:center;border-radius:1rem;background:var(--paper);box-shadow:inset 0 0 0 1px var(--border)}.network-illustration__logo img{width:2.75rem;border-radius:.6rem}.network-illustration__orchestrator strong{margin-top:.75rem;font-size:.7rem}.network-illustration__orchestrator small{margin-top:.18rem;color:var(--ink-500);font-size:.53rem}.network-illustration__fragments{display:flex;gap:.25rem;margin-top:.75rem}.network-illustration__fragments i{width:.42rem;height:.42rem;border-radius:.12rem;background:var(--mint-500)}.network-illustration__fragments i:nth-child(3n){background:var(--violet-500)}
.network-illustration__legend{position:absolute;bottom:1rem;left:1rem;z-index:3;display:flex;gap:.85rem;padding:.5rem .65rem;border:1px solid var(--border);border-radius:.65rem;background:rgba(255,255,255,.88);color:var(--ink-600);font-size:.55rem;font-weight:700}.network-illustration__legend span{display:flex;align-items:center;gap:.3rem}.network-illustration__legend i{width:.38rem;height:.38rem;border-radius:.1rem}.network-illustration__legend .mint{background:var(--mint-500)}.network-illustration__legend .violet{background:var(--violet-500)}.network-illustration__legend .ink{background:var(--ink-700)}
@media(max-width:720px){.network-illustration{min-height:390px}.network-illustration__paths{display:none}.network-illustration__node--input{top:5%;left:4%}.network-illustration__orchestrator{top:26%;left:calc(50% - 76px)}.network-illustration__node--worker{display:none}.network-illustration__node--worker:nth-of-type(4){display:grid;top:72%!important;left:4%!important}.network-illustration__node--worker:nth-of-type(5){display:grid;top:72%!important;left:calc(50% - 56px)!important}.network-illustration__node--result{top:72%;right:4%}.network-illustration__legend{top:1rem;right:1rem;bottom:auto;left:auto;align-items:flex-start;flex-direction:column;gap:.35rem}}
</style>
