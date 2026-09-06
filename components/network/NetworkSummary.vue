<template>
  <div class="network-summary">
    <div class="network-summary__core"><span class="network-summary__pulse"><i></i></span><div><span class="eyebrow">Mesh Silicium</span><strong>{{ peers.length }} nœud{{ peers.length > 1 ? 's' : '' }} recensé{{ peers.length > 1 ? 's' : '' }}</strong><small>Vue agrégée conçue pour rester lisible à grande échelle.</small></div></div>
    <div class="network-summary__groups"><div v-for="group in roleGroups.slice(0,4)" :key="group.role"><span>{{ group.count }}</span><small>{{ group.role }}</small></div><div><span>{{ outdatedCount }}</span><small>à mettre à jour</small></div></div>
  </div>
</template>

<script setup lang="ts">
import type { NetworkPeer } from '~/types/api';
defineProps<{ peers: NetworkPeer[]; roleGroups: { role: string; count: number }[]; outdatedCount: number }>();
</script>

<style scoped>
.network-summary{display:grid;grid-template-columns:1.15fr 1fr;gap:1rem;padding:1.25rem;border:1px solid var(--border);border-radius:var(--radius-lg);background:linear-gradient(135deg,#fff,var(--surface-soft));box-shadow:var(--shadow-sm)}.network-summary__core{display:flex;align-items:center;gap:1rem}.network-summary__pulse{display:grid;width:3.2rem;height:3.2rem;flex:0 0 auto;place-items:center;border-radius:50%;background:var(--mint-100)}.network-summary__pulse i{width:.7rem;height:.7rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 8px rgba(24,181,165,.12)}.network-summary__core strong,.network-summary__core small{display:block}.network-summary__core strong{margin-top:.38rem;font-size:1rem}.network-summary__core small{margin-top:.28rem;color:var(--ink-500);font-size:.62rem}.network-summary__groups{display:grid;grid-template-columns:repeat(5,1fr);align-items:center;border:1px solid var(--border);border-radius:.85rem;background:white}.network-summary__groups>div{padding:.7rem;text-align:center;border-right:1px solid var(--border)}.network-summary__groups>div:last-child{border:0}.network-summary__groups span,.network-summary__groups small{display:block}.network-summary__groups span{font-size:1rem;font-weight:800}.network-summary__groups small{margin-top:.25rem;color:var(--ink-500);font-size:.52rem;text-transform:capitalize}
@media(max-width:900px){.network-summary{grid-template-columns:1fr}.network-summary__groups{grid-template-columns:repeat(5,minmax(70px,1fr));overflow-x:auto}}@media(max-width:520px){.network-summary__core{align-items:flex-start}.network-summary__groups{grid-template-columns:repeat(5,82px)}}
</style>
