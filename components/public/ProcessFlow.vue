<template>
  <ol class="process-flow">
    <li v-for="(step,index) in steps" :key="step.title"><span>{{ String(index + 1).padStart(2,'0') }}</span><div class="process-flow__icon"><UiIcon :name="step.icon"/></div><h3>{{ step.title }}</h3><p>{{ step.text }}</p></li>
  </ol>
</template>

<script setup lang="ts">
const steps = [
  { title: 'Soumettre', text: 'Vous envoyez une charge de travail et ses paramètres depuis un espace sécurisé.', icon: 'upload' },
  { title: 'Distribuer', text: 'L’orchestrateur découpe le travail et sélectionne les rôles adaptés.', icon: 'layers' },
  { title: 'Vérifier', text: 'Les fragments sont calculés, attestés puis contrôlés avant acceptation.', icon: 'shield' },
  { title: 'Réassembler', text: 'Le résultat final et ses traces deviennent disponibles au même endroit.', icon: 'result' },
];
</script>

<style scoped>
.process-flow{display:grid;margin:0;padding:0;grid-template-columns:repeat(4,1fr);list-style:none;border:1px solid var(--border);border-radius:var(--radius-xl);background:white;box-shadow:var(--shadow-sm)}.process-flow li{position:relative;min-height:230px;padding:1.5rem;border-right:1px solid var(--border)}.process-flow li:last-child{border:0}.process-flow>li>span{color:var(--ink-300);font-size:.62rem;font-weight:800;letter-spacing:.08em}.process-flow__icon{display:grid;width:2.65rem;height:2.65rem;margin-top:2rem;place-items:center;border-radius:.78rem;background:var(--mint-100);color:var(--mint-700)}.process-flow li:nth-child(3) .process-flow__icon{background:var(--violet-100);color:var(--violet-600)}.process-flow__icon svg{width:1.15rem}.process-flow h3{margin:1rem 0 .5rem;font-size:.9rem;letter-spacing:-.02em}.process-flow p{margin:0;color:var(--ink-600);font-size:.72rem;line-height:1.7}
@media(max-width:800px){.process-flow{grid-template-columns:1fr 1fr}.process-flow li:nth-child(2){border-right:0}.process-flow li:nth-child(-n+2){border-bottom:1px solid var(--border)}}@media(max-width:480px){.process-flow{grid-template-columns:1fr}.process-flow li{display:grid;min-height:0;grid-template-columns:2.7rem 1fr;column-gap:1rem;border-right:0;border-bottom:1px solid var(--border)!important}.process-flow li>span{display:none}.process-flow__icon{grid-row:1/3;margin:0}.process-flow h3{margin:.05rem 0 .25rem}.process-flow p{grid-column:2}}
</style>
