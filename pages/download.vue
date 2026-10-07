<template>
  <div class="download-page marketing-page">
    <section class="download-hero marketing-container">
      <div class="download-hero__copy">
        <span class="marketing-kicker">{{ t('download.kicker') }}</span>
        <h1 class="marketing-title">{{ t('download.title') }}<br><em>{{ t('download.titleEm') }}</em></h1>
        <p class="marketing-lede">{{ t('download.lede') }}</p>
        <div class="download-hero__actions"><UiButton to="/auth?mode=register" size="large" icon="arrow">{{ t('download.createSpace') }}</UiButton><UiButton to="/service" variant="secondary" size="large">{{ t('download.understand') }}</UiButton></div>
      </div>
      <div class="release-highlight marketing-glass"><div class="release-highlight__top"><span>{{ t('download.recommended') }}</span><UiStatusBadge status="operational" :label="t('download.stable')" /></div><div class="release-highlight__body"><span class="release-highlight__icon"><UiIcon name="download" /></span><div><strong>{{ stableVersion }}</strong><small>{{ t('download.lastVerified') }}</small></div></div><dl><div><dt>{{ t('download.channel') }}</dt><dd>{{ t('download.stable') }}</dd></div><div><dt>{{ t('download.installation') }}</dt><dd>Windows</dd></div><div><dt>{{ t('download.status') }}</dt><dd>{{ t('download.compatible') }}</dd></div></dl></div>
    </section>

    <section class="release-section marketing-container">
      <div class="marketing-section-heading"><div><span class="marketing-kicker">{{ t('download.versionsKicker') }}</span><h2>{{ t('download.versionsTitle') }}<br>{{ t('download.versionsTitle2') }}</h2></div><p>{{ t('download.versionsText') }}</p></div>
      <UiNotice v-if="error" tone="warning">{{ error }} {{ t('download.errorSuffix') }}</UiNotice>
      <div class="release-grid">
        <article v-for="release in releases" :key="release.key" class="release-card" :class="`release-card--${release.tone}`">
          <div class="release-card__head"><span class="release-card__icon"><UiIcon :name="release.icon" /></span><UiStatusBadge :status="release.status" :label="release.channel" /></div>
          <div class="release-card__copy"><h3>{{ release.label }}</h3><p>{{ release.detail }}</p></div>
          <dl class="release-card__meta"><div><dt>{{ t('download.version') }}</dt><dd>{{ release.version }}</dd></div><div><dt>{{ t('download.format') }}</dt><dd>{{ release.format }}</dd></div><div><dt>{{ t('download.build') }}</dt><dd>{{ release.build || '—' }}</dd></div></dl>
          <UiButton :href="release.url" target="_blank" icon="download">{{ t('common.download') }}</UiButton>
        </article>
      </div>
      <p class="release-note">{{ t('download.note') }}</p>
    </section>

    <section class="package-install-section marketing-container marketing-glass" aria-labelledby="package-install-title">
      <div><span class="marketing-kicker">{{ t('download.nativeKicker') }}</span><h2 id="package-install-title">{{ t('download.nativeTitle') }}<br><em>{{ t('download.nativeTitleEm') }}</em></h2><p>{{ t('download.nativeText') }}</p></div>
      <div class="package-install-options">
        <article><div><strong>Debian · Ubuntu</strong><small>{{ t('download.debPackage') }}</small></div><code>sudo apt install ./silicium-node-linux-dev.deb</code><UiButton :href="linuxPackageUrls.deb" target="_blank" variant="secondary" icon="download">{{ t('download.downloadDeb') }}</UiButton></article>
        <article><div><strong>Fedora · RHEL</strong><small>{{ t('download.rpmPackage') }}</small></div><code>sudo dnf install ./silicium-node-linux-dev.rpm</code><UiButton :href="linuxPackageUrls.rpm" target="_blank" variant="secondary" icon="download">{{ t('download.downloadRpm') }}</UiButton></article>
      </div>
    </section>

    <section class="install-section marketing-container marketing-glass">
      <div><span class="marketing-kicker">{{ t('download.afterKicker') }}</span><h2>{{ t('download.afterTitle') }}<br><em>{{ t('download.afterTitleEm') }}</em></h2><p>{{ t('download.afterText') }}</p></div>
      <ol class="install-steps"><li v-for="(step, index) in tl<{ title: string; text: string }>('download.steps')" :key="index"><span>0{{ index + 1 }}</span><div><strong>{{ step.title }}</strong><small>{{ step.text }}</small></div></li></ol>
    </section>
  </div>
</template>

<script setup lang="ts">
import { resolveNodeDownloadUrl } from '~/utils/downloads';

definePageMeta({ layout: 'public' });
const config = useRuntimeConfig();
const { manifest, error, refresh } = useSystemStatus();
const stableRelease = computed(() => manifest.value?.channels?.prod || {});
const devRelease = computed(() => manifest.value?.channels?.dev || {});
const stableVersion = computed(() => stableRelease.value.version || 'stable');
const linuxPackageUrls = computed(() => ({
  deb: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevDebUrl, '/downloads/silicium-node-linux-dev.deb'),
  rpm: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevRpmUrl, '/downloads/silicium-node-linux-dev.rpm'),
}));
const { t, tl } = useI18n();
const release = (key: string) => ({
  label: t(`download.releases.${key}.label`), channel: t(`download.releases.${key}.channel`),
  detail: t(`download.releases.${key}.detail`), format: t(`download.releases.${key}.format`),
});
const releases = computed(() => [
  { key: 'windows-stable', ...release('windowsStable'), icon: 'windows', version: stableRelease.value.version || 'stable', build: stableRelease.value.build, url: resolveNodeDownloadUrl(config.public.nodeAppWindowsUrl, '/downloads/silicium-node-windows.exe'), status: 'operational', tone: 'stable' },
  { key: 'windows-dev', ...release('windowsDev'), icon: 'windows', version: devRelease.value.version || 'dev', build: devRelease.value.build, url: resolveNodeDownloadUrl(config.public.nodeAppWindowsDevUrl, '/downloads/silicium-node-windows-dev.exe'), status: 'degraded', tone: 'test' },
  { key: 'linux-dev', ...release('linuxDev'), icon: 'linux', version: devRelease.value.version || 'dev', build: devRelease.value.build, url: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevUrl, '/downloads/silicium-node-linux-dev.AppImage'), status: 'degraded', tone: 'test' },
  { key: 'linux-dev-deb', ...release('linuxDeb'), icon: 'linux', version: devRelease.value.version || 'dev', build: devRelease.value.build, url: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevDebUrl, '/downloads/silicium-node-linux-dev.deb'), status: 'degraded', tone: 'test' },
  { key: 'linux-dev-rpm', ...release('linuxRpm'), icon: 'linux', version: devRelease.value.version || 'dev', build: devRelease.value.build, url: resolveNodeDownloadUrl(config.public.nodeAppLinuxDevRpmUrl, '/downloads/silicium-node-linux-dev.rpm'), status: 'degraded', tone: 'test' },
]);
onMounted(() => refresh());
useSeoMeta({ title: () => t('download.seoTitle'), description: () => t('download.seoDescription') });
</script>

<style scoped>
.package-install-section{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);align-items:center;gap:clamp(2rem,6vw,6rem);margin-top:clamp(3rem,6vw,5rem);padding:clamp(1.5rem,3.5vw,2.8rem);border-radius:1.7rem;background:linear-gradient(120deg,rgba(255,255,255,.8),rgba(225,248,243,.6) 55%,rgba(238,236,255,.5))}.package-install-section h2{margin:.9rem 0 0;color:var(--ink-950);font-size:clamp(2rem,3.5vw,3.4rem);line-height:1;letter-spacing:-.06em}.package-install-section h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.package-install-section p{max-width:450px;margin:.9rem 0 0;color:var(--ink-700);font-size:.8rem;line-height:1.7}.package-install-options{display:grid;gap:.7rem}.package-install-options article{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:.9rem;padding:1rem;border:1px solid rgba(255,255,255,.78);border-radius:.9rem;background:rgba(255,255,255,.58)}.package-install-options strong,.package-install-options small{display:block}.package-install-options strong{font-size:.76rem}.package-install-options small{margin-top:.25rem;color:var(--ink-500);font-size:.61rem}.package-install-options code{grid-column:1/-1;padding:.62rem .7rem;border-radius:.55rem;background:rgba(21,40,61,.06);color:var(--ink-800);font-family:var(--font-mono);font-size:.59rem;overflow:auto}.package-install-options :deep(.ui-button){grid-column:2;grid-row:1}
.download-hero{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(24rem,.92fr);align-items:center;gap:clamp(2.5rem,7vw,7rem);min-height:min(670px,calc(100svh - 5rem));padding-block:clamp(3.5rem,7vw,6rem)}.download-hero__copy .marketing-title{max-width:720px;font-size:clamp(3rem,5vw,5.4rem)}.download-hero__copy .marketing-lede{max-width:620px}.download-hero__actions{display:flex;flex-wrap:wrap;gap:.7rem;margin-top:1.8rem}.release-highlight{overflow:hidden;border-radius:1.7rem;background:linear-gradient(145deg,rgba(255,255,255,.82),rgba(225,248,243,.58) 58%,rgba(238,236,255,.5))}.release-highlight__top{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.25rem;border-bottom:1px solid var(--border);color:var(--ink-500);font-family:var(--font-mono);font-size:.56rem;letter-spacing:.06em}.release-highlight__body{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.9rem;padding:1.5rem 1.25rem}.release-highlight__icon{display:grid;width:3.2rem;height:3.2rem;place-items:center;border-radius:.9rem;background:var(--mint-100);color:var(--mint-700)}.release-highlight__icon svg{width:1.25rem}.release-highlight__body strong,.release-highlight__body small{display:block}.release-highlight__body strong{color:var(--ink-950);font-family:var(--font-mono);font-size:1.15rem}.release-highlight__body small{margin-top:.35rem;color:var(--ink-600);font-size:.65rem}.release-highlight dl{display:grid;grid-template-columns:repeat(3,1fr);margin:0;padding:0 1.25rem 1.25rem}.release-highlight dl>div{padding-top:.75rem;border-top:1px solid var(--border)}.release-highlight dt,.release-highlight dd{font-size:.58rem}.release-highlight dt{color:var(--ink-500)}.release-highlight dd{margin:.28rem 0 0;color:var(--ink-900);font-weight:760}.release-section{padding-top:clamp(4rem,8vw,7rem)}.release-section>.ui-notice{margin-top:1.5rem}.release-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:2rem}.release-card{display:flex;min-width:0;flex-direction:column;padding:1.2rem;border:1px solid var(--glass-edge);border-radius:1.2rem;background:var(--glass-card);box-shadow:var(--glass-inset),var(--glass-shadow);backdrop-filter:blur(22px)}.release-card--stable{box-shadow:inset 0 0 0 1px rgba(18,191,174,.16),var(--glass-shadow)}.release-card__head{display:flex;align-items:center;justify-content:space-between;gap:.6rem}.release-card__icon{display:grid;width:2.5rem;height:2.5rem;place-items:center;border-radius:.7rem;background:var(--mint-100);color:var(--mint-700)}.release-card--test .release-card__icon{background:var(--violet-100);color:var(--violet-600)}.release-card__icon svg{width:1.1rem}.release-card__copy{min-height:7rem;margin-top:1.2rem}.release-card__copy h3{margin:0;color:var(--ink-950);font-size:.9rem;letter-spacing:-.03em}.release-card__copy p{margin:.5rem 0 0;color:var(--ink-600);font-size:.68rem;line-height:1.55}.release-card__meta{display:grid;grid-template-columns:1fr 1fr;margin:0 0 1rem}.release-card__meta>div{padding:.55rem 0;border-top:1px solid var(--border)}.release-card__meta>div:last-child{grid-column:1/-1}.release-card__meta dt{color:var(--ink-500);font-size:.55rem}.release-card__meta dd{margin:.22rem 0 0;overflow:hidden;color:var(--ink-900);font-family:var(--font-mono);font-size:.59rem;text-overflow:ellipsis;white-space:nowrap}.release-card :deep(.ui-button){width:100%;margin-top:auto}.release-note{max-width:800px;margin:1rem 0 0;color:var(--ink-500);font-size:.63rem;line-height:1.6}.install-section{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);align-items:center;gap:clamp(2rem,7vw,7rem);margin-top:clamp(4rem,8vw,7rem);padding:clamp(1.7rem,4vw,3.4rem);border-radius:1.7rem;background:linear-gradient(120deg,rgba(255,255,255,.82),rgba(225,248,243,.62) 55%,rgba(238,236,255,.55))}.install-section h2{margin:.9rem 0 0;color:var(--ink-950);font-size:clamp(2rem,3.8vw,3.6rem);line-height:1;letter-spacing:-.06em}.install-section h2 em{color:var(--ink-500);font-style:normal;font-weight:560}.install-section p{max-width:480px;margin:.9rem 0 0;color:var(--ink-700);font-size:.8rem;line-height:1.7}.install-steps{display:grid;gap:.7rem;margin:0;padding:0;list-style:none}.install-steps li{display:grid;grid-template-columns:2.3rem 1fr;gap:.8rem;padding:.85rem;border:1px solid rgba(255,255,255,.75);border-radius:.8rem;background:rgba(255,255,255,.58)}.install-steps li>span{color:var(--mint-700);font-family:var(--font-mono);font-size:.58rem}.install-steps strong,.install-steps small{display:block}.install-steps strong{font-size:.72rem}.install-steps small{margin-top:.25rem;color:var(--ink-600);font-size:.62rem;line-height:1.45}
@media(max-width:980px){.download-hero{grid-template-columns:1fr;min-height:auto;gap:3rem}.download-hero__copy{max-width:780px}.release-highlight{max-width:720px}.release-grid{grid-template-columns:1fr 1fr}.release-grid .release-card:first-child{grid-column:1/-1}.package-install-section{grid-template-columns:1fr;gap:2rem}.install-section{grid-template-columns:1fr;gap:2rem}}
@media(max-width:620px){.download-hero{padding-block:3rem 4rem}.download-hero__actions{align-items:stretch;flex-direction:column}.download-hero__actions :deep(.ui-button){width:100%}.release-grid{grid-template-columns:1fr}.release-grid .release-card:first-child{grid-column:auto}.release-card__copy{min-height:0}.release-highlight dl{gap:.5rem}.package-install-section{border-radius:1.3rem;padding:1.35rem}.package-install-options article{grid-template-columns:1fr}.package-install-options code{grid-column:1}.package-install-options :deep(.ui-button){grid-column:1;grid-row:auto;width:100%}.install-section{border-radius:1.3rem}.install-section{padding:1.35rem}}
</style>
