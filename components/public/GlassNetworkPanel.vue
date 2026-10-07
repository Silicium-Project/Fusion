<template>
  <section class="network-panel marketing-glass" :aria-label="t('glassPanel.aria')">
    <header class="network-panel__header">
      <div>
        <span class="network-panel__label">{{ t('glassPanel.label') }}</span>
        <strong>{{ networkStatusLabel }}</strong>
      </div>
      <span class="network-panel__status"><i aria-hidden="true"></i>{{ statusLabel(status?.network.status || 'unknown') }}</span>
    </header>

    <div class="network-panel__summary">
      <div>
        <span class="network-panel__eyebrow">{{ t('glassPanel.active') }}</span>
        <strong>{{ activePeers }} <small>/ {{ totalPeers }}</small></strong>
        <p>{{ t('glassPanel.known', { count: totalPeers }) }} · {{ updatedLabel }}</p>
      </div>
      <span class="network-panel__signal" :aria-label="t('glassPanel.networkState', { status: statusLabel(status?.network.status || 'unknown') })"><i></i><i></i><i></i><i></i><i></i></span>
    </div>

    <div class="network-panel__map" role="img" :aria-label="t('glassPanel.mapAria')">
      <span class="network-panel__map-caption">{{ t('glassPanel.running') }}</span>
      <svg viewBox="0 0 680 300" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="network-line" x1="90" y1="60" x2="600" y2="240" gradientUnits="userSpaceOnUse">
            <stop stop-color="#11bfae" stop-opacity=".18" />
            <stop offset=".5" stop-color="#11bfae" />
            <stop offset="1" stop-color="#796df0" stop-opacity=".7" />
          </linearGradient>
          <radialGradient id="network-core" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(340 150) rotate(90) scale(55)">
            <stop stop-color="#fff" stop-opacity=".98" />
            <stop offset="1" stop-color="#d8f7f3" stop-opacity=".26" />
          </radialGradient>
        </defs>
        <path class="network-panel__route" d="M82 76C169 77 198 121 280 145C303 151 319 151 340 150C391 148 421 116 496 86C535 70 578 80 603 105" stroke="url(#network-line)" stroke-width="2" />
        <path class="network-panel__route network-panel__route--secondary" d="M86 229C166 223 211 182 280 159C302 152 320 151 340 150C393 148 444 177 514 209C548 224 585 215 603 192" stroke="url(#network-line)" stroke-width="2" />
        <path class="network-panel__route network-panel__route--secondary" d="M175 44C220 83 246 107 280 145M503 42C450 73 407 103 340 150M175 256C225 211 252 180 280 159M508 258C454 214 402 178 340 150" stroke="url(#network-line)" stroke-width="1.5" />
        <circle cx="340" cy="150" r="42" fill="url(#network-core)" stroke="#fff" stroke-opacity=".9" />
        <circle cx="340" cy="150" r="54" stroke="#fff" stroke-opacity=".45" stroke-dasharray="2 8" />
        <path d="M326 151h28M340 137v28" stroke="#087d74" stroke-width="2" stroke-linecap="round" />
        <g class="network-panel__node network-panel__node--active"><circle cx="82" cy="76" r="7" /><circle cx="82" cy="76" r="13" /></g>
        <g class="network-panel__node network-panel__node--active"><circle cx="603" cy="105" r="7" /><circle cx="603" cy="105" r="13" /></g>
        <g class="network-panel__node network-panel__node--active"><circle cx="86" cy="229" r="7" /><circle cx="86" cy="229" r="13" /></g>
        <g class="network-panel__node network-panel__node--active"><circle cx="603" cy="192" r="7" /><circle cx="603" cy="192" r="13" /></g>
        <g class="network-panel__node"><circle cx="175" cy="44" r="6" /><circle cx="175" cy="44" r="11" /></g>
        <g class="network-panel__node network-panel__node--violet"><circle cx="503" cy="42" r="6" /><circle cx="503" cy="42" r="11" /></g>
        <g class="network-panel__node"><circle cx="175" cy="256" r="6" /><circle cx="175" cy="256" r="11" /></g>
        <g class="network-panel__node network-panel__node--violet"><circle cx="508" cy="258" r="6" /><circle cx="508" cy="258" r="11" /></g>
      </svg>
      <span class="network-panel__chip network-panel__chip--one">{{ t('glassPanel.control') }}</span>
      <span class="network-panel__chip network-panel__chip--two">{{ t('glassPanel.shared') }}</span>
    </div>

    <footer class="network-panel__metrics">
      <div><span>{{ t('glassPanel.cpu') }}</span><strong>{{ percent(status?.network.systemCpuPercent) }}</strong></div>
      <div><span>{{ t('glassPanel.queue') }}</span><strong>{{ integer(status?.network.queueDepth) }}</strong></div>
      <div><span>{{ t('glassPanel.toUpdate') }}</span><strong>{{ status?.network.outdatedPeers ?? '—' }}</strong></div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { formatDate, statusLabel } from '~/utils/format';

const { t } = useI18n();
const { status, refresh } = useSystemStatus();
const totalPeers = computed(() => status.value?.network.peers ?? 0);
const activePeers = computed(() => status.value?.network.activePeers ?? 0);
const networkStatusLabel = computed(() => statusLabel(status.value?.network.status || 'unknown'));
const updatedLabel = computed(() => status.value?.checkedAt ? t('glassPanel.updated', { date: formatDate(status.value.checkedAt) }) : t('glassPanel.waiting'));
const percent = (value: unknown): string => Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} %` : '—';
const integer = (value: unknown): string => Number.isFinite(Number(value)) ? String(Math.max(0, Math.round(Number(value)))) : '—';

onMounted(() => {
  if (!status.value) refresh().catch(() => undefined);
});
</script>

<style scoped>
.network-panel{border-radius:2rem;padding:1.1rem;background:linear-gradient(145deg,rgba(255,255,255,.82),rgba(227,249,245,.5) 55%,rgba(239,237,255,.54));box-shadow:var(--glass-inset),0 32px 82px rgba(31,54,72,.15);-webkit-backdrop-filter:blur(30px) saturate(1.3);backdrop-filter:blur(30px) saturate(1.3)}
.network-panel::after{position:absolute;top:-35%;right:-14%;width:58%;aspect-ratio:1;border:1px solid rgba(255,255,255,.6);border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.48),transparent 68%);content:'';pointer-events:none}
.network-panel__header{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;padding:.55rem .65rem 1.4rem;border-bottom:1px solid rgba(21,40,61,.08)}.network-panel__label,.network-panel__header strong{display:block}.network-panel__label{color:var(--ink-500);font-family:var(--font-mono);font-size:.58rem;letter-spacing:.08em;text-transform:uppercase}.network-panel__header strong{margin-top:.35rem;color:var(--ink-900);font-size:.9rem;letter-spacing:-.02em}.network-panel__status{display:inline-flex;align-items:center;gap:.45rem;padding:.4rem .62rem;border:1px solid rgba(18,191,174,.2);border-radius:999px;background:rgba(225,248,243,.7);color:var(--mint-800);font-size:.62rem;font-weight:760}.network-panel__status i{width:.4rem;height:.4rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .22rem rgba(18,191,174,.12);animation:network-pulse 2.4s ease-in-out infinite}
.network-panel__summary{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;padding:1.6rem .65rem 1rem}.network-panel__eyebrow{display:block;color:var(--ink-500);font-size:.63rem;font-weight:700;letter-spacing:.03em}.network-panel__summary strong{display:block;margin-top:.45rem;color:var(--ink-900);font-size:clamp(2.4rem,5vw,4rem);font-weight:630;letter-spacing:-.075em;line-height:1}.network-panel__summary strong small{color:var(--ink-500);font-size:.82rem;font-weight:700;letter-spacing:-.02em}.network-panel__summary p{margin:.55rem 0 0;color:var(--ink-600);font-size:.67rem;line-height:1.5}.network-panel__signal{display:flex;align-items:flex-end;gap:.22rem;height:2.3rem;padding-bottom:.2rem}.network-panel__signal i{width:.25rem;border-radius:99px;background:var(--mint-500)}.network-panel__signal i:nth-child(1){height:28%;opacity:.3}.network-panel__signal i:nth-child(2){height:46%;opacity:.48}.network-panel__signal i:nth-child(3){height:64%;opacity:.65}.network-panel__signal i:nth-child(4){height:82%;opacity:.8}.network-panel__signal i:nth-child(5){height:100%}
.network-panel__map{position:relative;overflow:hidden;min-height:18rem;border:1px solid rgba(255,255,255,.8);border-radius:1.25rem;background:linear-gradient(145deg,rgba(255,255,255,.55),rgba(210,244,239,.28));box-shadow:inset 0 1px 0 rgba(255,255,255,.9),inset 0 0 0 1px rgba(21,40,61,.05)}.network-panel__map::before{position:absolute;inset:0;background:linear-gradient(90deg,rgba(21,40,61,.045) 1px,transparent 1px) 0 0/2.5rem 2.5rem,linear-gradient(rgba(21,40,61,.045) 1px,transparent 1px) 0 0/2.5rem 2.5rem;mask-image:linear-gradient(90deg,transparent,black 12%,black 88%,transparent);content:''}.network-panel__map::after{position:absolute;top:0;bottom:0;left:-20%;width:18%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.5),transparent);transform:skewX(-20deg);animation:network-scan 7s ease-in-out infinite;content:'';pointer-events:none}.network-panel__map svg{position:absolute;inset:1.6rem .45rem .2rem;width:calc(100% - .9rem);height:calc(100% - 1.8rem)}.network-panel__map-caption{position:absolute;z-index:1;top:.8rem;left:.9rem;color:var(--ink-500);font-family:var(--font-mono);font-size:.55rem;letter-spacing:.07em;text-transform:uppercase}.network-panel__route{stroke-dasharray:4 7;animation:network-flow 9s linear infinite}.network-panel__route--secondary{opacity:.55;animation-duration:13s}.network-panel__node circle:first-child{fill:#fff;stroke:var(--ink-300);stroke-width:1.5}.network-panel__node circle:last-child{fill:none;stroke:var(--ink-300);stroke-opacity:.3;stroke-dasharray:2 4}.network-panel__node--active circle:first-child{fill:var(--mint-500);stroke:#fff}.network-panel__node--active circle:last-child{stroke:var(--mint-500);stroke-opacity:.48}.network-panel__node--violet circle:first-child{fill:var(--violet-500);stroke:#fff}.network-panel__node--violet circle:last-child{stroke:var(--violet-500);stroke-opacity:.4}.network-panel__chip{position:absolute;z-index:2;padding:.35rem .5rem;border:1px solid rgba(255,255,255,.8);border-radius:.55rem;background:rgba(255,255,255,.7);color:var(--ink-600);font-family:var(--font-mono);font-size:.52rem;box-shadow:var(--shadow-xs);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}.network-panel__chip--one{top:26%;left:4%}.network-panel__chip--two{right:4%;bottom:20%}
.network-panel__metrics{display:grid;grid-template-columns:repeat(3,1fr);margin-top:1rem;padding:.35rem .65rem .15rem}.network-panel__metrics>div{padding:.6rem .8rem;border-right:1px solid rgba(21,40,61,.08)}.network-panel__metrics>div:first-child{padding-left:0}.network-panel__metrics>div:last-child{border:0;padding-right:0}.network-panel__metrics span,.network-panel__metrics strong{display:block}.network-panel__metrics span{color:var(--ink-500);font-size:.6rem}.network-panel__metrics strong{margin-top:.35rem;color:var(--ink-900);font-size:1rem;font-weight:630;letter-spacing:-.04em}.network-panel__metrics small{color:var(--ink-500);font-size:.58rem;font-weight:600}
@keyframes network-pulse{50%{box-shadow:0 0 0 .38rem rgba(18,191,174,0),0 0 15px rgba(18,191,174,.4)}}@keyframes network-scan{0%,25%{left:-20%;opacity:0}40%{opacity:1}75%,100%{left:115%;opacity:0}}@keyframes network-flow{to{stroke-dashoffset:-88}}
@media(max-width:620px){.network-panel{padding:.75rem;border-radius:1.5rem}.network-panel__summary{padding-top:1.35rem}.network-panel__map{min-height:15rem}.network-panel__map svg{inset:1.6rem -.6rem 0;width:calc(100% + 1.2rem);height:calc(100% - 1.6rem)}.network-panel__chip{display:none}.network-panel__metrics{padding-inline:.25rem}.network-panel__metrics>div{padding-inline:.55rem}.network-panel__metrics span{font-size:.56rem}.network-panel__metrics strong{font-size:.88rem}}
@media(prefers-reduced-motion:reduce){.network-panel__status i,.network-panel__route,.network-panel__map::after{animation:none}}
</style>
