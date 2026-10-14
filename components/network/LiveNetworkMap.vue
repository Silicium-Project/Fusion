<template>
  <section v-tilt="1.25" class="live-network-map tilt-surface" :class="{ 'live-network-map--compact': compact }" aria-labelledby="live-network-map-title">
    <header class="live-network-map__header">
      <div>
        <div class="live-network-map__kicker"><span class="eyebrow">{{ t('liveMap.eyebrow') }}</span><span class="live-network-map__live-badge"><i></i> {{ lastUpdatedAt ? t('liveMap.live') : t('liveMap.waiting') }}</span></div>
        <h2 id="live-network-map-title">{{ t('liveMap.title') }}</h2>
        <p>{{ t('liveMap.text') }}</p>
      </div>
      <div class="live-network-map__updated" aria-live="polite"><span class="live-network-map__updated-dot"></span><span>{{ t('liveMap.updated') }} <strong>{{ updatedLabel }}</strong></span></div>
    </header>

    <div class="live-network-map__stage" role="img" :aria-label="t('liveMap.aria', { active: activeNodes, total: totalNodes, count: activeWorkloads })">
      <div class="live-network-map__stage-grid" aria-hidden="true"></div>
      <div class="live-network-map__scan" aria-hidden="true"></div>
      <svg class="live-network-map__paths" viewBox="0 0 900 380" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="liveNetworkPath" x1="0" x2="1">
            <stop offset="0" stop-color="#12bfae" stop-opacity=".14" />
            <stop offset=".5" stop-color="#12bfae" stop-opacity=".78" />
            <stop offset="1" stop-color="#796df0" stop-opacity=".4" />
          </linearGradient>
          <filter id="liveNetworkGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <path id="live-path-left-top" d="M450 190 C365 128 285 76 135 74" />
        <path id="live-path-left-bottom" d="M450 190 C350 240 260 289 135 302" />
        <path id="live-path-right-top" d="M450 190 C550 126 642 78 768 82" />
        <path id="live-path-right-bottom" d="M450 190 C555 244 638 294 770 302" />
        <path class="live-network-map__cross-link" d="M135 74 C260 45 628 44 768 82" />
        <path class="live-network-map__cross-link" d="M135 302 C302 342 628 344 770 302" />
        <circle cx="310" cy="103" r="3.5" />
        <circle cx="596" cy="109" r="3.5" />
        <circle cx="308" cy="268" r="3.5" />
        <circle cx="610" cy="273" r="3.5" />
        <g class="live-network-map__packets" filter="url(#liveNetworkGlow)">
          <circle r="5" fill="#12bfae"><animateMotion dur="4.4s" begin="-.8s" repeatCount="indefinite"><mpath href="#live-path-left-top" /></animateMotion></circle>
          <circle r="4" fill="#796df0"><animateMotion dur="5.4s" begin="-2.6s" repeatCount="indefinite"><mpath href="#live-path-right-top" /></animateMotion></circle>
          <circle r="4.5" fill="#12bfae"><animateMotion dur="4.9s" begin="-1.9s" repeatCount="indefinite"><mpath href="#live-path-left-bottom" /></animateMotion></circle>
          <circle r="4" fill="#796df0"><animateMotion dur="5.8s" begin="-3.7s" repeatCount="indefinite"><mpath href="#live-path-right-bottom" /></animateMotion></circle>
        </g>
      </svg>

      <article v-for="node in mapNodes" :key="node.key" class="live-network-map__node" :class="`live-network-map__node--${node.tone}`" :style="node.style">
        <span class="live-network-map__node-icon"><UiIcon :name="node.icon" /></span>
        <div><small>{{ node.kicker }}</small><strong>{{ node.label }}</strong><em>{{ node.detail }}</em></div>
        <b class="mono">{{ node.value }}</b>
      </article>

      <div class="live-network-map__core">
        <span class="live-network-map__core-orbit" aria-hidden="true"></span>
        <span class="live-network-map__core-mark"><UiIcon name="network" /></span>
        <small>{{ t('liveMap.coordination') }}</small>
        <strong>{{ activeNodes }}</strong>
        <span>{{ t('liveMap.activeMachines') }}</span>
      </div>

      <div class="live-network-map__legend" aria-hidden="true"><span><i class="is-mint"></i> {{ t('roles.compute') }}</span><span><i class="is-violet"></i> {{ t('roles.verify') }}</span><span><i class="is-ink"></i> {{ t('roles.storage') }}</span></div>
    </div>

    <footer class="live-network-map__telemetry" :aria-label="t('liveMap.telemetry')">
      <div><span class="live-network-map__telemetry-label"><i></i> {{ t('liveMap.cpu') }}</span><strong class="mono">{{ percent(metrics.system_cpu_percent) }}</strong><small>{{ t('liveMap.instrumented', { count: metrics.telemetry_nodes || 0 }) }}</small></div>
      <div><span class="live-network-map__telemetry-label"><i></i> {{ t('liveMap.memory') }}</span><strong class="mono">{{ percent(metrics.system_memory_percent) }}</strong><small>{{ t('liveMap.cores', { count: metrics.logical_cpu_count || 0 }) }}</small></div>
      <div><span class="live-network-map__telemetry-label"><i></i> {{ t('liveMap.queue') }}</span><strong class="mono">{{ integer(metrics.queue_depth) }}</strong><small>{{ t('liveMap.tasks', { count: integer(metrics.active_tasks), projects: activeWorkloads }) }}</small></div>
      <div v-if="bars.length" class="live-network-map__bars" aria-hidden="true"><span v-for="(bar, index) in bars" :key="index" :style="{ height: `${bar}%`, animationDelay: `${index * -120}ms` }"></span></div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import type { NetworkMetrics } from '~/types/api';
import { formatDate, networkRoleGroup, type NetworkRoleGroup } from '~/utils/format';

interface RoleGroup { role: string; count: number }

interface Props {
  totalNodes?: number;
  activeNodes?: number;
  activeWorkloads?: number;
  roleGroups?: RoleGroup[];
  networkMetrics?: NetworkMetrics;
  lastUpdatedAt?: string | null;
  compact?: boolean;
}

const props = defineProps<Props>();
const { t } = useI18n();
const totalNodes = computed(() => Math.max(0, Math.round(Number(props.totalNodes) || 0)));
const activeNodes = computed(() => Math.max(0, Math.round(Number(props.activeNodes) || 0)));
const activeWorkloads = computed(() => Math.max(0, Math.round(Number(props.activeWorkloads) || 0)));
const metrics = computed<NetworkMetrics>(() => props.networkMetrics || {});
const updatedLabel = computed(() => props.lastUpdatedAt ? formatDate(props.lastUpdatedAt) : t('liveMap.noObservation'));
const percent = (value: unknown): string => Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} %` : '—';
const integer = (value: unknown): string => Number.isFinite(Number(value)) ? String(Math.max(0, Math.round(Number(value)))) : '—';

const groups = computed(() => (props.roleGroups || []).filter(group => group.count > 0));
const countForRole = (role: NetworkRoleGroup): number => groups.value.filter(group => networkRoleGroup(group.role) === role).reduce((total, group) => total + group.count, 0);
const detailForRole = (role: NetworkRoleGroup): string => countForRole(role) ? t('liveMap.announced') : t('liveMap.noData');

const mapNodes = computed(() => [
  { key: 'orchestrator', kicker: t('liveMap.planning'), label: t('roles.orchestration'), detail: detailForRole('orchestration'), value: String(countForRole('orchestration')), icon: 'layers', tone: 'mint', style: { '--node-x': '5%', '--node-y': '12%', '--node-delay': '0ms' } },
  { key: 'compute', kicker: t('liveMap.activePool'), label: t('roles.compute'), detail: detailForRole('compute'), value: String(countForRole('compute')), icon: 'processor', tone: 'mint', style: { '--node-x': '5%', '--node-y': '65%', '--node-delay': '-900ms' } },
  { key: 'verify', kicker: t('liveMap.guard'), label: t('roles.verify'), detail: detailForRole('verify'), value: String(countForRole('verify')), icon: 'shield', tone: 'violet', style: { '--node-x': '78%', '--node-y': '14%', '--node-delay': '-1.5s' } },
  { key: 'storage', kicker: t('liveMap.output'), label: t('roles.storage'), detail: detailForRole('storage'), value: String(countForRole('storage')), icon: 'database', tone: 'ink', style: { '--node-x': '78%', '--node-y': '66%', '--node-delay': '-2.2s' } },
]);

const bars = computed(() => {
  return [metrics.value.system_cpu_percent, metrics.value.system_memory_percent, metrics.value.storage_used_percent]
    .filter((value): value is number => Number.isFinite(Number(value)))
    .map(value => Math.max(12, Math.min(100, Number(value))));
});
</script>

<style scoped>
.live-network-map{position:relative;overflow:hidden;border:1px solid var(--glass-edge);border-radius:var(--radius-xl);background:var(--glass-card);box-shadow:var(--glass-inset),var(--shadow-lg);backdrop-filter:blur(30px) saturate(1.35)}
.live-network-map::before{position:absolute;inset:0;background:radial-gradient(circle at 52% 46%,rgba(18,191,174,.1),transparent 27%),radial-gradient(circle at 83% 10%,rgba(121,109,240,.12),transparent 24%);content:'';pointer-events:none}.live-network-map::after{position:absolute;z-index:4;inset:0;background:linear-gradient(110deg,transparent 25%,rgba(255,255,255,.3) 47%,transparent 67%);transform:translateX(-100%);animation:live-map-sheen 9s ease-in-out infinite;content:'';pointer-events:none}
.live-network-map__header{position:relative;z-index:5;display:flex;align-items:flex-start;justify-content:space-between;gap:1.5rem;padding:1.55rem 1.65rem 1.15rem}.live-network-map__kicker{display:flex;align-items:center;gap:.7rem}.live-network-map__live-badge{display:inline-flex;align-items:center;gap:.35rem;padding:.33rem .52rem;border:1px solid rgba(18,191,174,.18);border-radius:99px;background:rgba(225,248,243,.72);color:var(--mint-800);font-size:.853rem;font-weight:800}.live-network-map__live-badge i,.live-network-map__updated-dot{width:.4rem;height:.4rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 4px rgba(18,191,174,.1),0 0 18px rgba(18,191,174,.5);animation:live-dot 2.2s ease-in-out infinite}.live-network-map h2{margin:.55rem 0 0;font-size:clamp(1.35rem,2.3vw,2rem);line-height:1.05;letter-spacing:-.055em}.live-network-map__header p{max-width:470px;margin:.55rem 0 0;color:var(--ink-600);font-size:.905rem;line-height:1.6}.live-network-map__updated{display:flex;align-items:center;gap:.55rem;padding:.58rem .7rem;border:1px solid rgba(255,255,255,.78);border-radius:99px;background:rgba(255,255,255,.56);box-shadow:inset 0 0 0 1px rgba(11,21,35,.05);color:var(--ink-500);font-size:.857rem;white-space:nowrap;backdrop-filter:blur(14px)}.live-network-map__updated strong{color:var(--ink-800)}
.live-network-map__stage{position:relative;min-height:380px;margin:0 .85rem;border:1px solid rgba(255,255,255,.74);border-radius:1.4rem;background:rgba(248,251,249,.4);box-shadow:inset 0 1px 0 rgba(255,255,255,.82),inset 0 0 0 1px rgba(11,21,35,.045);isolation:isolate}.live-network-map__stage-grid{position:absolute;inset:0;opacity:.62;background-image:linear-gradient(rgba(23,34,49,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(23,34,49,.055) 1px,transparent 1px);background-size:32px 32px;mask-image:radial-gradient(ellipse,#000 10%,transparent 80%);pointer-events:none}.live-network-map__scan{position:absolute;z-index:1;top:0;bottom:0;left:27%;width:18%;background:linear-gradient(90deg,transparent,rgba(18,191,174,.055),transparent);transform:skewX(-18deg);animation:live-scan 8s ease-in-out infinite;pointer-events:none}.live-network-map__paths{position:absolute;z-index:2;inset:0;width:100%;height:100%;overflow:visible}.live-network-map__paths path{fill:none;stroke:url(#liveNetworkPath);stroke-width:1.6;stroke-dasharray:6 8;animation:live-path 12s linear infinite}.live-network-map__paths .live-network-map__cross-link{stroke:rgba(18,191,174,.13);stroke-width:1;stroke-dasharray:3 9;animation-duration:18s}.live-network-map__paths circle{fill:white;stroke:var(--mint-500);stroke-width:1.6;filter:drop-shadow(0 0 5px rgba(18,191,174,.45));animation:live-node 2.8s ease-in-out infinite}.live-network-map__packets circle{stroke:0;animation:none}
.live-network-map__node{position:absolute;z-index:4;left:var(--node-x);top:var(--node-y);display:grid;width:164px;min-height:70px;grid-template-columns:auto 1fr auto;align-items:center;gap:.55rem;padding:.65rem;border:1px solid rgba(255,255,255,.86);border-radius:1rem;background:rgba(255,255,255,.7);box-shadow:inset 0 0 0 1px var(--border),inset 0 1px 0 white,0 16px 30px rgba(19,32,51,.1);backdrop-filter:blur(18px) saturate(1.3);animation:live-node-float 5.2s var(--ease-out) infinite;animation-delay:var(--node-delay)}.live-network-map__node::before{position:absolute;inset:-1px;border:1px solid transparent;border-radius:inherit;background:linear-gradient(135deg,rgba(255,255,255,.7),transparent 55%) border-box;mask:linear-gradient(#000 0 0) padding-box,linear-gradient(#000 0 0);mask-composite:exclude;content:'';pointer-events:none}.live-network-map__node-icon{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.62rem;background:var(--mint-100);color:var(--mint-700);box-shadow:inset 0 0 0 1px rgba(18,191,174,.12),0 7px 18px rgba(18,191,174,.1)}.live-network-map__node--violet .live-network-map__node-icon{background:var(--violet-100);color:var(--violet-600);box-shadow:inset 0 0 0 1px rgba(121,109,240,.12),0 7px 18px rgba(121,109,240,.1)}.live-network-map__node--ink .live-network-map__node-icon{background:var(--ink-100);color:var(--ink-700);box-shadow:inset 0 0 0 1px rgba(11,21,35,.08),0 7px 18px rgba(19,32,51,.08)}.live-network-map__node svg{width:.85rem}.live-network-map__node small,.live-network-map__node strong,.live-network-map__node em{display:block}.live-network-map__node small{color:var(--ink-500);font-size:.812rem;font-style:normal;font-weight:820;letter-spacing:.08em}.live-network-map__node strong{margin-top:.15rem;font-size:.867rem;letter-spacing:-.02em}.live-network-map__node em{margin-top:.12rem;color:var(--ink-500);font-size:.819rem;font-style:normal}.live-network-map__node b{color:var(--ink-400);font-size:.857rem}
.live-network-map__core{position:absolute;z-index:5;top:50%;left:50%;display:flex;width:148px;height:148px;align-items:center;justify-content:center;flex-direction:column;border:1px solid rgba(255,255,255,.92);border-radius:2.5rem;background:linear-gradient(145deg,rgba(255,255,255,.92),rgba(241,250,247,.7));box-shadow:inset 0 0 0 1px var(--border),inset 0 1px 0 white,0 22px 45px rgba(19,32,51,.16);transform:translate(-50%,-50%) translateZ(32px);backdrop-filter:blur(22px) saturate(1.3)}.live-network-map__core-orbit{position:absolute;inset:-18px;border:1px solid rgba(18,191,174,.16);border-radius:2.9rem;box-shadow:0 0 0 9px rgba(18,191,174,.025);animation:live-orbit 4.6s ease-in-out infinite}.live-network-map__core-mark{display:grid;width:3rem;height:3rem;place-items:center;border:1px solid rgba(18,191,174,.18);border-radius:1rem;background:linear-gradient(145deg,var(--mint-100),white);color:var(--mint-700);box-shadow:inset 0 0 0 1px rgba(255,255,255,.84),0 10px 20px rgba(18,191,174,.13)}.live-network-map__core-mark svg{width:1.25rem}.live-network-map__core small{margin-top:.65rem;color:var(--ink-500);font-size:.812rem;font-weight:820;letter-spacing:.12em}.live-network-map__core strong{margin-top:.12rem;font-family:var(--font-display);font-size:1.15rem;letter-spacing:-.05em}.live-network-map__core>span:last-child{margin-top:.12rem;color:var(--ink-500);font-size:.83rem}.live-network-map__legend{position:absolute;z-index:5;right:1rem;bottom:.9rem;left:1rem;display:flex;gap:.85rem;color:var(--ink-500);font-size:.83rem}.live-network-map__legend span{display:flex;align-items:center;gap:.32rem}.live-network-map__legend i{width:.38rem;height:.38rem;border-radius:.12rem}.live-network-map__legend .is-mint{background:var(--mint-500)}.live-network-map__legend .is-violet{background:var(--violet-500)}.live-network-map__legend .is-ink{background:var(--ink-700)}
.live-network-map__telemetry{position:relative;z-index:5;display:grid;grid-template-columns:repeat(3,1fr) auto;align-items:center;gap:1rem;padding:1.1rem 1.65rem 1.35rem}.live-network-map__telemetry>div:not(.live-network-map__bars){display:grid;gap:.25rem;padding-right:1rem;border-right:1px solid var(--border)}.live-network-map__telemetry-label{display:flex;align-items:center;gap:.38rem;color:var(--ink-500);font-size:.847rem}.live-network-map__telemetry-label i{width:.33rem;height:.33rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 3px rgba(18,191,174,.1)}.live-network-map__telemetry strong{font-family:var(--font-display);font-size:.983rem;letter-spacing:-.04em}.live-network-map__telemetry small{color:var(--ink-500);font-size:.83rem}.live-network-map__bars{display:flex;align-items:flex-end;justify-content:flex-end;gap:.22rem;height:2.8rem;min-width:100px}.live-network-map__bars span{display:block;width:.25rem;min-height:.5rem;border-radius:99px;background:linear-gradient(to top,var(--mint-500),var(--violet-500));transform-origin:bottom;animation:live-bars 1.8s ease-in-out infinite}
.live-network-map--compact .live-network-map__stage{min-height:320px}.live-network-map--compact .live-network-map__header{padding-bottom:.8rem}.live-network-map--compact .live-network-map__telemetry{padding-top:.8rem}
@keyframes live-map-sheen{0%,38%{transform:translateX(-100%)}72%,100%{transform:translateX(160%)}}@keyframes live-dot{50%{box-shadow:0 0 0 7px rgba(18,191,174,0),0 0 24px rgba(18,191,174,.68)}}@keyframes live-path{to{stroke-dashoffset:-180}}@keyframes live-node{50%{transform:scale(1.45);opacity:.42}}@keyframes live-node-float{50%{transform:translateY(-4px)}}@keyframes live-orbit{50%{transform:scale(1.045);opacity:.5}}@keyframes live-scan{0%,100%{transform:translateX(-20%) skewX(-18deg);opacity:0}35%,65%{opacity:1}50%{transform:translateX(360%) skewX(-18deg)}}@keyframes live-bars{50%{transform:scaleY(.58);opacity:.72}}
@media(prefers-reduced-motion:reduce){.live-network-map__packets{display:none}.live-network-map::after,.live-network-map__scan,.live-network-map__node,.live-network-map__core-orbit,.live-network-map__bars span{animation:none}}
@media(max-width:760px){.live-network-map__header{padding:1.25rem 1.1rem .9rem}.live-network-map__header p{font-size:.884rem}.live-network-map__updated{align-self:flex-start;font-size:.836rem}.live-network-map__stage{min-height:360px;margin:0 .55rem}.live-network-map__node{width:132px;min-height:62px;padding:.5rem;gap:.4rem}.live-network-map__node-icon{width:1.7rem;height:1.7rem}.live-network-map__node strong{font-size:.847rem}.live-network-map__node em{font-size:.812rem}.live-network-map__node b{font-size:.836rem}.live-network-map__node[style*="--node-x: 78%"]{left:auto;right:3%}.live-network-map__node[style*="--node-x: 5%"]{left:3%}.live-network-map__core{width:126px;height:126px;border-radius:2rem}.live-network-map__core-orbit{border-radius:2.35rem}.live-network-map__legend{right:.7rem;bottom:.7rem;left:.7rem;gap:.5rem;font-size:.812rem}.live-network-map__telemetry{grid-template-columns:1fr 1fr;gap:.7rem;padding:1rem 1.1rem 1.1rem}.live-network-map__telemetry>div:not(.live-network-map__bars){padding-right:.5rem}.live-network-map__telemetry>div:nth-child(2){border-right:0}.live-network-map__telemetry>div:nth-child(3){border-top:1px solid var(--border);border-right:0;padding-top:.7rem}.live-network-map__bars{display:none}}
@media(max-width:480px){.live-network-map__header{display:block}.live-network-map__updated{display:inline-flex;margin-top:.8rem}.live-network-map__stage{min-height:350px}.live-network-map__node{width:124px}.live-network-map__core{width:112px;height:112px}.live-network-map__core-mark{width:2.55rem;height:2.55rem}.live-network-map__core strong{font-size:1rem}.live-network-map__core small{font-size:.812rem}.live-network-map__core>span:last-child{font-size:.816rem}.live-network-map__paths{opacity:.78}}
.live-network-map{-webkit-backdrop-filter:blur(30px) saturate(1.4);backdrop-filter:blur(30px) saturate(1.4)}.live-network-map__header p{font-size:.932rem;line-height:1.68}.live-network-map__updated{-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
</style>
