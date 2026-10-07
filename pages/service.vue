<template>
  <div v-if="!isDownloadPage" class="service-page marketing-page">
    <section class="service-hero marketing-container">
      <div v-reveal="'left'" class="service-hero__copy">
        <span class="marketing-kicker">{{ t('service.kicker') }}</span>
        <h1 class="marketing-title">{{ t('service.title') }}<br><em>{{ t('service.titleEm') }}</em></h1>
        <p class="marketing-lede">{{ t('service.lede') }}</p>
        <div class="marketing-action-row"><UiButton to="#status" size="large" icon="arrow">{{ t('service.seeStatus') }}</UiButton><UiButton to="/download" variant="secondary" size="large">{{ t('common.installNode') }}</UiButton></div>
      </div>
      <div v-reveal="'right'" class="service-console marketing-glass">
        <header class="service-console__header"><div><span class="service-console__label">{{ t('service.consoleLabel') }}</span><strong>{{ t('service.consoleTitle') }}</strong></div><span class="service-console__badge"><i></i>{{ t('service.consoleBadge') }}</span></header>
        <div class="service-console__list">
          <article v-for="(layer, index) in layers" :key="layer.number"><span class="service-console__index">{{ layer.number }}</span><span class="service-console__icon"><UiIcon :name="layer.icon" /></span><div><strong>{{ layer.title }}</strong><p>{{ layer.text }}</p></div><span class="service-console__state">{{ index === 3 ? t('service.stateOut') : t('service.stateActive') }}</span></article>
        </div>
        <footer class="service-console__footer"><span><i></i>{{ t('service.lastUpdate') }}</span><span class="mono">{{ status?.checkedAt ? formatDate(status.checkedAt) : '—' }}</span></footer>
      </div>
    </section>

    <section class="service-flow marketing-container marketing-section">
      <div v-reveal class="marketing-section-heading"><div><span class="marketing-kicker">{{ t('service.flowKicker') }}</span><h2>{{ t('service.flowTitle') }}<br>{{ t('service.flowTitle2') }}</h2></div><p>{{ t('service.flowText') }}</p></div>
      <ProcessFlow />
    </section>

    <section id="status" class="status-section marketing-container marketing-section--tight">
      <div class="status-section__head"><div><span class="marketing-kicker">{{ t('service.nowKicker') }}</span><h2>{{ t('service.nowTitle') }}</h2><p>{{ t('service.updated', { date: status ? formatDate(status.checkedAt) : t('service.updating') }) }}</p></div><UiButton variant="secondary" size="small" icon="refresh" :loading="loading" @click="refresh(true)">{{ t('common.refresh') }}</UiButton></div>
      <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
      <div class="status-board marketing-glass"><article v-for="item in statusItems" :key="item.key"><div class="status-board__mark"><UiIcon :name="item.icon" /></div><div class="status-board__main"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><p>{{ item.detail }}</p></div><UiStatusBadge :status="item.status" /></article></div>
    </section>

    <section id="downloads" class="downloads marketing-container marketing-section--tight">
      <div class="downloads__intro"><span class="marketing-kicker">{{ t('service.contributorsKicker') }}</span><h2>{{ t('service.contributorsTitle') }}<br><em>{{ t('service.contributorsTitleEm') }}</em></h2><p>{{ t('service.contributorsText') }}</p></div>
      <div class="downloads__list">
        <a :href="nodeDownloadUrls.windows" :aria-label="t('service.ariaWindowsStable')">
          <span class="downloads__platform downloads__platform--windows"><UiIcon name="windows" /></span>
          <div><strong>{{ t('service.windowsStable') }}</strong><small>{{ t('service.stableVersion', { version: stableVersion }) }}</small></div>
          <UiIcon name="arrow" />
        </a>
        <a :href="nodeDownloadUrls.windowsDev" :aria-label="t('service.ariaWindowsTest')">
          <span class="downloads__platform downloads__platform--windows downloads__platform--violet"><UiIcon name="windows" /></span>
          <div><strong>{{ t('service.windowsTest') }}</strong><small>{{ t('service.testVersion', { version: devVersion }) }}</small></div>
          <UiIcon name="arrow" />
        </a>
        <a :href="nodeDownloadUrls.linuxDev" :aria-label="t('service.ariaLinuxTest')">
          <span class="downloads__platform downloads__platform--linux downloads__platform--graphite"><UiIcon name="linux" /></span>
          <div><strong>{{ t('service.linuxTest') }}</strong><small>AppImage · {{ devVersion }}</small></div>
          <UiIcon name="arrow" />
        </a>
        <a :href="nodeDownloadUrls.linuxDevDeb" :aria-label="t('service.ariaLinuxDeb')">
          <span class="downloads__platform downloads__platform--linux downloads__platform--graphite"><UiIcon name="linux" /></span>
          <div><strong>{{ t('service.linuxDeb') }}</strong><small>.deb · {{ devVersion }}</small></div>
          <UiIcon name="arrow" />
        </a>
        <a :href="nodeDownloadUrls.linuxDevRpm" :aria-label="t('service.ariaLinuxRpm')">
          <span class="downloads__platform downloads__platform--linux downloads__platform--graphite"><UiIcon name="linux" /></span>
          <div><strong>{{ t('service.linuxRpm') }}</strong><small>.rpm · {{ devVersion }}</small></div>
          <UiIcon name="arrow" />
        </a>
      </div>
    </section>
  </div>
  <NuxtPage />
</template>

<script setup lang="ts">
import { formatDate, statusLabel } from '~/utils/format';
import { resolveNodeDownloadUrl } from '~/utils/downloads';
definePageMeta({ layout: 'public' });
const config = useRuntimeConfig();
const route = useRoute();
const isDownloadPage = computed(() => route.path.startsWith('/service/downloads/'));
const { status, manifest, loading, error, refresh } = useSystemStatus();
const nodeDownloadUrls = computed(() => ({
  windows: resolveNodeDownloadUrl(config.public.nodeAppWindowsUrl, '/downloads/silicium-node-windows.exe'),
  windowsDev: resolveNodeDownloadUrl(config.public.nodeAppWindowsDevUrl, '/downloads/silicium-node-windows-dev.exe'),
  linuxDev: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevUrl, '/downloads/silicium-node-linux-dev.AppImage'),
  linuxDevDeb: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevDebUrl, '/downloads/silicium-node-linux-dev.deb'),
  linuxDevRpm: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevRpmUrl, '/downloads/silicium-node-linux-dev.rpm'),
}));
const { t, tl } = useI18n();
const layerIcons = ['code', 'layers', 'network', 'shield'];
const layers = computed(() => tl<{ title: string; text: string }>('service.layers').map((layer, index) => ({ ...layer, number: `0${index + 1}`, icon: layerIcons[index] || 'code' })));
const statusItems = computed(() => [
  { key: 'backend', label: 'Silicium', status: status.value?.backend.status || 'unknown', value: statusLabel(status.value?.backend.status), detail: t('service.statusBackend'), icon: 'code' },
  { key: 'network', label: t('service.statusNetwork'), status: status.value?.network.status || 'unknown', value: status.value ? t('service.activeMachines', { count: status.value.network.activePeers }) : '—', detail: status.value ? t('service.pendingUpdates', { count: status.value.network.outdatedPeers }) : t('service.telemetryUnavailable'), icon: 'network' },
  { key: 'payments', label: t('service.payments'), status: status.value?.blockchain.status || 'unknown', value: blockchainNetwork.value, detail: status.value?.blockchain.configured ? t('service.paymentsReady') : t('service.paymentsPreparing'), icon: 'shield' },
]);
const blockchainNetwork = computed(() => { const value = status.value?.blockchain.network || 'unknown'; return value.charAt(0).toUpperCase() + value.slice(1); });
const stableVersion = computed(() => manifest.value?.channels?.prod?.version || t('common.unavailable'));
const devVersion = computed(() => manifest.value?.channels?.dev?.version || t('common.unavailable'));
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { refresh(); timer = setInterval(() => refresh(), Math.max(10, Number(config.public.statusRefreshSeconds) || 30) * 1000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); });
useSeoMeta({ title: () => t('service.seoTitle'), description: () => t('service.seoDescription') });
</script>

<style scoped>
.service-hero{display:grid;grid-template-columns:minmax(0,1.04fr) minmax(26rem,.96fr);align-items:center;gap:clamp(2.5rem,5vw,5rem);min-height:min(700px,calc(100svh - 5rem));padding-block:clamp(3.5rem,7vw,6rem)}.service-hero__copy{min-width:0}.service-hero__copy .marketing-title{max-width:700px;font-size:clamp(3rem,4.7vw,5.2rem)}
.service-console{border-radius:1.8rem;padding:1.1rem;background:linear-gradient(145deg,rgba(255,255,255,.8),rgba(225,248,243,.52) 58%,rgba(238,236,255,.48))}.service-console__header{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;padding:.5rem .55rem 1.25rem;border-bottom:1px solid var(--border)}.service-console__label,.service-console__header strong{display:block}.service-console__label{color:var(--ink-500);font-family:var(--font-mono);font-size:.58rem;letter-spacing:.06em;text-transform:uppercase}.service-console__header strong{margin-top:.35rem;color:var(--ink-900);font-size:1rem;letter-spacing:-.03em}.service-console__badge{display:inline-flex;align-items:center;gap:.4rem;padding:.38rem .55rem;border:1px solid rgba(18,191,174,.18);border-radius:99px;background:rgba(225,248,243,.7);color:var(--mint-800);font-size:.58rem;font-weight:750}.service-console__badge i,.service-console__footer i{width:.38rem;height:.38rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .22rem rgba(18,191,174,.1)}.service-console__list{display:grid;gap:.55rem;padding:1.1rem 0}.service-console__list article{display:grid;grid-template-columns:1.4rem 2.3rem 1fr auto;align-items:center;gap:.7rem;padding:.75rem;border:1px solid rgba(255,255,255,.75);border-radius:.85rem;background:rgba(255,255,255,.55);transition:transform .3s var(--ease-spring),background .3s ease}.service-console__list article:hover{transform:translateX(4px);background:rgba(255,255,255,.82)}.service-console__index{color:var(--ink-400);font-family:var(--font-mono);font-size:.55rem}.service-console__icon{display:grid;width:2.3rem;height:2.3rem;place-items:center;border-radius:.7rem;background:var(--mint-100);color:var(--mint-700)}.service-console__list article:nth-child(3) .service-console__icon,.service-console__list article:nth-child(4) .service-console__icon{background:var(--violet-100);color:var(--violet-600)}.service-console__icon svg{width:.95rem}.service-console__list strong,.service-console__list p{display:block}.service-console__list strong{color:var(--ink-900);font-size:.72rem}.service-console__list p{margin:.22rem 0 0;color:var(--ink-600);font-size:.61rem;line-height:1.45}.service-console__state{color:var(--mint-700);font-family:var(--font-mono);font-size:.5rem;letter-spacing:.05em}.service-console__footer{display:flex;align-items:center;justify-content:space-between;padding:.75rem .55rem .25rem;border-top:1px solid var(--border);color:var(--ink-600);font-size:.6rem}.service-console__footer span:first-child{display:inline-flex;align-items:center;gap:.42rem}.service-console__footer .mono{color:var(--ink-500);font-size:.58rem}
.service-flow{padding-top:clamp(4.5rem,8vw,8rem)}.status-section{display:grid;gap:1.25rem}.status-section__head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem}.status-section h2{margin:.85rem 0 0;color:var(--ink-900);font-size:clamp(2.4rem,4vw,4rem);font-weight:640;letter-spacing:-.065em}.status-section__head p{margin:.55rem 0 0;color:var(--ink-600);font-size:.75rem}.status-board{display:grid;border-radius:1.5rem;background:linear-gradient(135deg,rgba(255,255,255,.78),rgba(226,248,244,.38))}.status-board article{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:1rem;padding:1.15rem 1.35rem;border-bottom:1px solid var(--border)}.status-board article:last-child{border-bottom:0}.status-board__mark{display:grid;width:2.7rem;height:2.7rem;place-items:center;border-radius:.8rem;background:var(--mint-100);color:var(--mint-700)}.status-board article:nth-child(3) .status-board__mark{background:var(--violet-100);color:var(--violet-600)}.status-board__mark svg{width:1.05rem}.status-board__main span,.status-board__main strong,.status-board__main p{display:block}.status-board__main span{color:var(--ink-500);font-size:.64rem;font-weight:720}.status-board__main strong{margin-top:.28rem;color:var(--ink-900);font-size:.9rem;letter-spacing:-.02em}.status-board__main p{margin:.22rem 0 0;color:var(--ink-600);font-size:.68rem;line-height:1.5}
.downloads{display:grid;grid-template-columns:minmax(0,.78fr) minmax(0,1.22fr);gap:clamp(3rem,8vw,8rem);align-items:start}.downloads__intro h2{margin:.85rem 0 0;color:var(--ink-900);font-size:clamp(2.5rem,4.8vw,4.6rem);font-weight:640;line-height:.96;letter-spacing:-.07em}.downloads__intro h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.downloads__intro p{max-width:450px;margin:1.3rem 0 0;color:var(--ink-700);font-size:1rem;line-height:1.8}.downloads__list{display:grid;gap:.7rem}.downloads__list a{display:grid;grid-template-columns:3rem 1fr auto;align-items:center;gap:1rem;padding:1rem;border:1px solid var(--glass-edge);border-radius:1rem;background:rgba(255,255,255,.58);box-shadow:var(--glass-inset),var(--shadow-sm);transition:transform .3s var(--ease-spring),box-shadow .3s ease,background .3s ease}.downloads__list a:hover{transform:translateX(5px);background:rgba(255,255,255,.86);box-shadow:var(--glass-inset),var(--shadow-md)}.downloads__platform{display:grid;width:3rem;height:3rem;place-items:center;border-radius:.85rem;background:var(--mint-100);color:var(--mint-700);font-size:.6rem;font-weight:650}.downloads__platform svg{width:1.25rem;height:1.25rem}.downloads__platform--violet{background:var(--violet-100);color:var(--violet-600)}.downloads__platform--graphite{background:var(--ink-100);color:var(--ink-800)}.downloads__list strong,.downloads__list small{display:block}.downloads__list strong{color:var(--ink-900);font-size:.8rem}.downloads__list small{margin-top:.28rem;color:var(--ink-600);font-size:.65rem}.downloads__list>a>svg{width:.95rem;color:var(--ink-500)}
@media(max-width:1050px){.service-hero{grid-template-columns:1fr;min-height:auto;gap:3.5rem}.service-hero__copy{max-width:780px}.service-console{max-width:780px;width:100%;margin-inline:auto}.downloads{gap:3rem}}
@media(max-width:760px){.service-hero{padding-block:3.5rem 4.5rem}.service-console__list article{grid-template-columns:1.2rem 2.3rem 1fr}.service-console__state{display:none}.downloads{grid-template-columns:1fr}.status-section__head{align-items:flex-start;flex-direction:column}}
@media(max-width:520px){.service-hero{padding-block:3rem 4rem}.service-console{padding:.75rem;border-radius:1.35rem}.service-console__header{padding-inline:.4rem}.service-console__badge{font-size:.52rem}.service-console__list article{padding:.65rem}.service-console__list p{font-size:.58rem}.status-board{border-radius:1.2rem}.status-board article{grid-template-columns:auto 1fr;gap:.75rem;padding:1rem}.status-board article :deep(.status-badge){grid-column:2;justify-self:start}.downloads__list a{grid-template-columns:2.6rem 1fr auto;padding:.85rem}.downloads__platform{width:2.6rem;height:2.6rem}.downloads__intro h2{font-size:clamp(2.55rem,13vw,4rem)}}
</style>
