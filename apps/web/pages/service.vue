<template>
  <div v-if="!isDownloadPage" class="service-page marketing-page">
    <section class="service-hero marketing-container">
      <div v-reveal="'left'" class="service-hero__copy">
        <span class="marketing-kicker">{{ t('service.kicker') }}</span>
        <h1 class="marketing-title">
          {{ t('service.title') }}<br /><em>{{ t('service.titleEm') }}</em>
        </h1>
        <p class="marketing-lede">{{ t('service.lede') }}</p>
        <div class="marketing-action-row">
          <UiButton to="/jobs/new" size="large" icon="arrow">{{
            t('experience.home.start')
          }}</UiButton
          ><UiButton to="#status" variant="secondary" size="large">{{
            t('service.seeStatus')
          }}</UiButton>
        </div>
      </div>
      <LiveMetricsPanel />
    </section>

    <section class="service-flow marketing-container marketing-section">
      <div v-reveal class="marketing-section-heading">
        <div>
          <span class="marketing-kicker">{{ t('service.flowKicker') }}</span>
          <h2>{{ t('service.flowTitle') }}<br />{{ t('service.flowTitle2') }}</h2>
        </div>
        <p>{{ t('service.flowText') }}</p>
      </div>
      <NetworkBlueprint />
      <details class="service-walkthrough" @toggle="toggleWalkthrough">
        <summary>{{ t('experience.walkthrough.open') }}<UiIcon name="chevron" /></summary>
        <p>{{ t('experience.walkthrough.note') }}</p>
        <LazyProcessFlow v-if="walkthroughOpen" />
      </details>
    </section>

    <section id="mesure" class="service-measure marketing-container marketing-section">
      <div class="marketing-section-heading">
        <div>
          <span class="marketing-kicker">{{ t('observability.value.kicker') }}</span>
          <h2>{{ t('observability.value.costTitle') }}</h2>
        </div>
        <p>{{ t('observability.value.costIntro') }}</p>
      </div>
      <div class="service-measure__grid">
        <article
          v-for="(item, index) in tl<{ title: string; text: string }>(
            'observability.value.benefits',
          )"
          :key="item.title"
        >
          <span class="mono">0{{ index + 1 }}</span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
        </article>
      </div>
      <div class="service-measure__cost marketing-glass">
        <div>
          <strong>{{ t('observability.value.payment') }}</strong
          ><span>— {{ t('observability.value.paymentMissing') }}</span>
        </div>
        <p>{{ t('observability.value.unitsNote') }}</p>
        <UiButton to="/jobs" variant="secondary" icon="arrow">{{
          t('observability.value.details')
        }}</UiButton>
      </div>
    </section>
    <section id="status" class="status-section marketing-container marketing-section--tight">
      <div class="status-section__head">
        <div>
          <span class="marketing-kicker">{{ t('service.nowKicker') }}</span>
          <h2>{{ t('service.nowTitle') }}</h2>
          <p>
            {{
              t('service.updated', {
                date: status ? formatDate(status.checkedAt) : t('service.updating'),
              })
            }}
          </p>
        </div>
        <UiButton
          variant="secondary"
          size="small"
          icon="refresh"
          :loading="loading"
          @click="refresh(true)"
          >{{ t('common.refresh') }}</UiButton
        >
      </div>
      <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
      <div class="status-board marketing-glass">
        <article v-for="item in statusItems" :key="item.key">
          <div class="status-board__mark"><UiIcon :name="item.icon" /></div>
          <div class="status-board__main">
            <span>{{ item.label }}</span
            ><strong>{{ item.value }}</strong>
            <p>{{ item.detail }}</p>
          </div>
          <UiStatusBadge :status="item.status" />
        </article>
      </div>
    </section>

    <section id="downloads" class="downloads marketing-container marketing-section--tight">
      <div class="downloads__intro">
        <span class="marketing-kicker">{{ t('service.contributorsKicker') }}</span>
        <h2>
          {{ t('service.contributorsTitle') }}<br /><em>{{ t('service.contributorsTitleEm') }}</em>
        </h2>
        <p>{{ t('service.contributorsText') }}</p>
      </div>
      <div class="downloads__list">
        <a :href="nodeDownloadUrls.windows" :aria-label="t('service.ariaWindowsStable')">
          <span class="downloads__platform downloads__platform--windows"
            ><UiIcon name="windows"
          /></span>
          <div>
            <strong>{{ t('service.windowsStable') }}</strong
            ><small>{{ t('service.stableVersion', { version: stableVersion }) }}</small>
          </div>
          <UiIcon name="arrow" />
        </a>
        <a :href="nodeDownloadUrls.windowsDev" :aria-label="t('service.ariaWindowsTest')">
          <span class="downloads__platform downloads__platform--windows downloads__platform--violet"
            ><UiIcon name="windows"
          /></span>
          <div>
            <strong>{{ t('service.windowsTest') }}</strong
            ><small>{{ t('service.testVersion', { version: devVersion }) }}</small>
          </div>
          <UiIcon name="arrow" />
        </a>
        <a :href="nodeDownloadUrls.linuxDev" :aria-label="t('service.ariaLinuxTest')">
          <span class="downloads__platform downloads__platform--linux downloads__platform--graphite"
            ><UiIcon name="linux"
          /></span>
          <div>
            <strong>{{ t('service.linuxTest') }}</strong
            ><small>AppImage · {{ devVersion }}</small>
          </div>
          <UiIcon name="arrow" />
        </a>
        <NuxtLink
          to="/download?platform=linux&amp;manager=apt#installation"
          aria-label="APT — Debian / Ubuntu"
        >
          <span class="downloads__platform downloads__platform--linux"
            ><UiIcon name="linux"
          /></span>
          <div>
            <strong>Debian / Ubuntu</strong
            ><small>APT · {{ t('experience.download.native') }}</small>
          </div>
          <UiIcon name="arrow" />
        </NuxtLink>
        <NuxtLink
          to="/download?platform=linux&amp;manager=dnf#installation"
          aria-label="DNF — Fedora / RHEL"
        >
          <span class="downloads__platform downloads__platform--linux"
            ><UiIcon name="linux"
          /></span>
          <div>
            <strong>Fedora / RHEL</strong><small>DNF · {{ t('experience.download.native') }}</small>
          </div>
          <UiIcon name="arrow" />
        </NuxtLink>
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
  windows: resolveNodeDownloadUrl(
    config.public.nodeAppWindowsUrl,
    '/downloads/silicium-node-windows.exe',
  ),
  windowsDev: resolveNodeDownloadUrl(
    config.public.nodeAppWindowsDevUrl,
    '/downloads/silicium-node-windows-dev.exe',
  ),
  linuxDev: resolveNodeDownloadUrl(
    config.public.nodeAppLinuxDevUrl,
    '/downloads/silicium-node-linux-dev.AppImage',
  ),
}));
const { t, tl } = useI18n();
const walkthroughOpen = ref(false);
function toggleWalkthrough(event: Event) {
  walkthroughOpen.value = (event.currentTarget as HTMLDetailsElement).open;
}
const networkAvailable = computed(
  () => status.value && !['unknown', 'unavailable'].includes(status.value.network.status),
);
const statusItems = computed(() => [
  {
    key: 'backend',
    label: 'Silicium',
    status: status.value?.backend.status || 'unknown',
    value: statusLabel(status.value?.backend.status),
    detail: t('service.statusBackend'),
    icon: 'code',
  },
  {
    key: 'network',
    label: t('service.statusNetwork'),
    status: status.value?.network.status || 'unknown',
    value: networkAvailable.value
      ? t('service.activeMachines', { count: status.value!.network.activePeers })
      : '—',
    detail: networkAvailable.value
      ? t('service.pendingUpdates', { count: status.value!.network.outdatedPeers })
      : t('service.telemetryUnavailable'),
    icon: 'network',
  },
  {
    key: 'payments',
    label: t('service.payments'),
    status: status.value?.blockchain.status || 'unknown',
    value: blockchainNetwork.value,
    detail: status.value?.blockchain.configured
      ? t('service.paymentsReady')
      : t('service.paymentsPreparing'),
    icon: 'shield',
  },
]);
const blockchainNetwork = computed(() => {
  const value = status.value?.blockchain.network || 'unknown';
  return value.charAt(0).toUpperCase() + value.slice(1);
});
const stableVersion = computed(
  () => manifest.value?.channels?.prod?.version || t('common.unavailable'),
);
const devVersion = computed(
  () => manifest.value?.channels?.dev?.version || t('common.unavailable'),
);
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  refresh();
  timer = setInterval(
    () => refresh(),
    Math.max(10, Number(config.public.statusRefreshSeconds) || 30) * 1000,
  );
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
useSeoMeta({ title: () => t('service.seoTitle'), description: () => t('service.seoDescription') });
</script>

<style scoped>
.service-measure__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2.5rem;
}
.service-measure__grid article > span {
  font-size: 1rem;
  color: var(--mint-700);
}
.service-measure__grid h3 {
  margin: 1rem 0 0.7rem;
  font-size: 1.25rem;
  font-weight: 600;
}
.service-measure__grid p {
  margin: 0;
  color: var(--ink-600);
  font-size: 1.0625rem;
  line-height: 1.8;
}
.service-measure__cost {
  padding: 1.75rem;
  margin-top: 2.5rem;
  border-radius: 1rem;
}
.service-measure__cost > div {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1rem;
  font-size: 1.125rem;
}
.service-measure__cost > div span {
  color: var(--ink-600);
}
.service-measure__cost > p {
  max-width: 64rem;
  margin: 1rem 0 1.3rem;
  color: var(--ink-600);
  font-size: 1rem;
  line-height: 1.8;
}
@media (max-width: 700px) {
  .service-measure__grid {
    grid-template-columns: 1fr;
    gap: 2rem;
  }
  .service-measure__cost {
    padding: 1.25rem;
  }
}

.service-walkthrough {
  border: 1px solid var(--glass-edge);
  border-radius: 1rem;
  background: var(--glass-card);
}
.service-walkthrough > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  min-height: 4.5rem;
  padding: 1.25rem 1.5rem;
  cursor: pointer;
  list-style: none;
  color: var(--ink-800);
  font-size: 1rem;
}
.service-walkthrough > summary::-webkit-details-marker {
  display: none;
}
.service-walkthrough > summary svg {
  width: 1rem;
  transform: rotate(90deg);
}
.service-walkthrough[open] > summary svg {
  transform: rotate(-90deg);
}
.service-walkthrough > p {
  margin: 0;
  padding: 0 1.5rem 1.25rem;
  color: var(--ink-500);
  font-size: 1rem;
  line-height: 1.7;
}

.service-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.04fr) minmax(26rem, 0.96fr);
  align-items: start;
  gap: clamp(2.5rem, 5vw, 5rem);
  min-height: min(700px, calc(100svh - 5rem));
  padding-block: clamp(3.5rem, 7vw, 6rem);
}
.service-hero__copy {
  min-width: 0;
}
.service-hero__copy .marketing-title {
  max-width: 700px;
  font-size: clamp(2.7rem, 4.4vw, 4.4rem);
}
.service-flow {
  padding-top: 1rem;
}
.service-walkthrough {
  margin-top: 1.5rem;
}
.status-section {
  display: grid;
  gap: 1.25rem;
}
.status-section__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
}
.status-section h2 {
  margin: 0.85rem 0 0;
  color: var(--ink-900);
  font-size: clamp(2rem, 3.2vw, 3rem);
  font-weight: 640;
  letter-spacing: -0.065em;
}
.status-section__head p {
  margin: 0.55rem 0 0;
  color: var(--ink-600);
  font-size: 1rem;
}
.status-board {
  display: grid;
  border-radius: 1.5rem;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.78), rgba(239, 246, 255, 0.38));
}
.status-board article {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 1rem;
  padding: 1.15rem 1.35rem;
  border-bottom: 1px solid var(--border);
}
.status-board article:last-child {
  border-bottom: 0;
}
.status-board__mark {
  display: grid;
  width: 2.7rem;
  height: 2.7rem;
  place-items: center;
  border-radius: 0.8rem;
  background: var(--mint-100);
  color: var(--mint-700);
}
.status-board article:nth-child(3) .status-board__mark {
  background: var(--violet-100);
  color: var(--violet-600);
}
.status-board__mark svg {
  width: 1.05rem;
}
.status-board__main span,
.status-board__main strong,
.status-board__main p {
  display: block;
}
.status-board__main span {
  color: var(--ink-500);
  font-size: 0.9375rem;
  font-weight: 720;
}
.status-board__main strong {
  margin-top: 0.28rem;
  color: var(--ink-900);
  font-size: 0.966rem;
  letter-spacing: -0.02em;
}
.status-board__main p {
  margin: 0.22rem 0 0;
  color: var(--ink-600);
  font-size: 1rem;
  line-height: 1.5;
}
.downloads {
  display: grid;
  grid-template-columns: minmax(0, 0.78fr) minmax(0, 1.22fr);
  gap: clamp(3rem, 8vw, 8rem);
  align-items: start;
}
.downloads__intro h2 {
  margin: 0.85rem 0 0;
  color: var(--ink-900);
  font-size: clamp(2rem, 3.2vw, 3rem);
  font-weight: 640;
  line-height: 0.96;
  letter-spacing: -0.07em;
}
.downloads__intro h2 em {
  color: var(--ink-500);
  font-style: normal;
  font-weight: 560;
}
.downloads__intro p {
  max-width: 450px;
  margin: 1.3rem 0 0;
  color: var(--ink-700);
  font-size: 1rem;
  line-height: 1.8;
}
.downloads__list {
  display: grid;
  gap: 0.7rem;
}
.downloads__list a {
  display: grid;
  grid-template-columns: 3rem 1fr auto;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--glass-edge);
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: var(--glass-inset), var(--shadow-sm);
  transition:
    transform 0.3s var(--ease-spring),
    box-shadow 0.3s ease,
    background 0.3s ease;
}
.downloads__list a:hover {
  background: rgba(255, 255, 255, 0.86);
  box-shadow: var(--glass-inset), var(--shadow-md);
}
.downloads__platform {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  border-radius: 0.85rem;
  background: var(--mint-100);
  color: var(--mint-700);
  font-size: 0.9375rem;
  font-weight: 650;
}
.downloads__platform svg {
  width: 1.25rem;
  height: 1.25rem;
}
.downloads__platform--violet {
  background: var(--violet-100);
  color: var(--violet-600);
}
.downloads__platform--graphite {
  background: var(--ink-100);
  color: var(--ink-800);
}
.downloads__list strong,
.downloads__list small {
  display: block;
}
.downloads__list strong {
  color: var(--ink-900);
  font-size: 0.9375rem;
}
.downloads__list small {
  margin-top: 0.28rem;
  color: var(--ink-600);
  font-size: 0.9375rem;
}
.downloads__list > a > svg {
  width: 0.95rem;
  color: var(--ink-500);
}
@media (max-width: 1050px) {
  .service-hero {
    grid-template-columns: 1fr;
    min-height: auto;
    gap: 3.5rem;
  }
  .service-hero__copy {
    max-width: 780px;
  }
  .downloads {
    gap: 3rem;
  }
}
@media (max-width: 760px) {
  .service-hero {
    padding-block: 3.5rem 4.5rem;
  }
  .downloads {
    grid-template-columns: 1fr;
  }
  .status-section__head {
    align-items: flex-start;
    flex-direction: column;
  }
}
@media (max-width: 520px) {
  .service-hero {
    padding-block: 3rem 4rem;
  }
  .status-board {
    border-radius: 1.2rem;
  }
  .status-board article {
    grid-template-columns: auto 1fr;
    gap: 0.75rem;
    padding: 1rem;
  }
  .status-board article :deep(.status-badge) {
    grid-column: 2;
    justify-self: start;
  }
  .downloads__list a {
    grid-template-columns: 2.6rem 1fr auto;
    padding: 0.85rem;
  }
  .downloads__platform {
    width: 2.6rem;
    height: 2.6rem;
  }
  .downloads__intro h2 {
    font-size: clamp(2rem, 7vw, 3rem);
  }
}
</style>
