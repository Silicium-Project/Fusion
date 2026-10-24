<template>
  <div class="download-page marketing-page">
    <header class="download-heading marketing-container">
      <span class="marketing-kicker">{{ t('experience.download.kicker') }}</span>
      <h1>{{ t('experience.download.title') }}<br><em>{{ t('experience.download.titleEm') }}</em></h1>
      <p>{{ t('experience.download.description') }}</p>
    </header>
    <section id="installation" class="install-workspace marketing-container">
      <aside class="install-config">
        <div><span class="install-config__label">{{ t('experience.download.system') }}</span>
          <div class="platform-options" role="group" :aria-label="t('experience.download.system')">
            <button v-for="os in systems" :key="os" type="button" :aria-pressed="platform === os" @click="platform = os"><UiIcon :name="os" />{{ t('experience.download.' + os) }}<UiIcon v-if="platform === os" name="check" /></button>
          </div>
        </div>
        <div><span class="install-config__label">{{ t('experience.download.channel') }}</span>
          <div class="channel-options" role="group" :aria-label="t('experience.download.channel')">
            <button type="button" :aria-pressed="channel === 'prod'" @click="channel = 'prod'">{{ t('experience.download.stable') }}</button>
            <button type="button" :aria-pressed="channel === 'dev'" @click="channel = 'dev'">{{ t('experience.download.dev') }}</button>
          </div>
          <p>{{ t(channel === 'prod' ? 'experience.download.stableText' : 'experience.download.devText') }}</p>
        </div>
        <dl><div><dt>{{ t('experience.download.version') }}</dt><dd>{{ version }}</dd></div><div><dt>{{ t('experience.download.arch') }}</dt><dd>x86_64 / amd64</dd></div></dl>
        <NuxtLink to="/workers" class="install-config__status"><UiIcon name="processor" />{{ t('observability.worker.nav') }}<UiIcon name="arrow" /></NuxtLink>
        <NuxtLink to="/service#status" class="install-config__status"><UiIcon name="activity" />{{ t('experience.live.view') }}<UiIcon name="arrow" /></NuxtLink>
      </aside>
      <div class="install-content">
        <template v-if="platform === 'linux'">
          <div class="install-content__heading"><span class="marketing-kicker">Linux / {{ channel === 'prod' ? t('experience.download.stable') : t('experience.download.dev') }}</span><h2>{{ t('experience.download.native') }}</h2><p>{{ t('experience.download.nativeText') }}</p></div>
          <RepositoryInstaller :channel="channel" :initial-manager="route.query.manager === 'dnf' ? 'dnf' : 'apt'" />
          <p class="install-content__note">{{ t('experience.download.repoNote') }}</p>
          <details class="portable-download"><summary>{{ t('experience.download.portable') }}</summary><p>{{ t('experience.download.portableText') }}</p><UiButton :href="appImageUrl" target="_blank" variant="secondary" icon="download">{{ t('experience.download.portableAction') }}</UiButton></details>
        </template>
        <div v-else class="windows-install">
          <div class="windows-install__visual" aria-hidden="true"><img src="/brand/silicium-icon.svg" alt="" width="64" height="64"><span>Silicium Node</span></div>
          <span class="marketing-kicker">Windows / {{ channel === 'prod' ? t('experience.download.stable') : t('experience.download.dev') }}</span>
          <h2>Silicium Node <span>{{ version }}</span></h2>
          <p>{{ t('experience.download.windowsText') }}</p>
          <aside v-if="channel === 'dev'" class="windows-install__dev"><UiIcon name="network" />{{ t('experience.repos.devText') }}</aside>
          <UiButton :href="windowsUrl" target="_blank" size="large" icon="download">{{ t('experience.download.windowsAction') }}</UiButton>
        </div>
      </div>
    </section>
    <section class="after-install marketing-container marketing-section">
      <div class="after-install__heading"><h2>{{ t('experience.download.afterTitle') }}</h2><UiButton to="/workers/overview" variant="secondary" icon="arrow">{{ t('observability.worker.open') }}</UiButton></div>
      <ol><li v-for="(step, index) in tl<{title: string; text: string}>('experience.download.steps')" :key="step.title"><span>0{{ index + 1 }}</span><h3>{{ step.title }}</h3><p>{{ step.text }}</p></li></ol>
    </section>
  </div>
</template>

<script setup lang="ts">
import { resolveNodeDownloadUrl } from '~/utils/downloads';
import { PACKAGE_BASES, type PackageChannel } from '~/utils/packageRepositories';
definePageMeta({ layout: 'public' });
const config = useRuntimeConfig();
const route = useRoute();
const { t, tl } = useI18n();
const { manifest, refresh } = useSystemStatus();
const systems = ['linux', 'windows'] as const;
const platform = ref<'linux' | 'windows'>(route.query.platform === 'windows' ? 'windows' : 'linux');
const channel = ref<PackageChannel>(route.query.channel === 'prod' ? 'prod' : route.query.channel === 'dev' ? 'dev' : config.public.releaseChannel === 'prod' ? 'prod' : 'dev');
const version = computed(() => manifest.value?.channels?.[channel.value]?.version || t('experience.download.versionUnknown'));
function artifact(value: unknown, filename: string) {
  const path = resolveNodeDownloadUrl(value, '/downloads/' + filename);
  return path.startsWith('/downloads/') ? PACKAGE_BASES[channel.value] + path.slice('/downloads'.length) : path;
}
const windowsUrl = computed(() => channel.value === 'prod' ? artifact(config.public.nodeAppWindowsUrl, 'silicium-node-windows.exe') : artifact(config.public.nodeAppWindowsDevUrl, 'silicium-node-windows-dev.exe'));
const appImageUrl = computed(() => channel.value === 'prod' ? PACKAGE_BASES.prod + '/silicium-node-linux.AppImage' : artifact(config.public.nodeAppLinuxDevUrl, 'silicium-node-linux-dev.AppImage'));
onMounted(() => refresh());
useSeoMeta({ title: () => t('experience.download.seo'), description: () => t('experience.download.description') });
</script>

<style scoped>
.download-heading{padding-block:clamp(3rem,6vw,5rem);text-align:left}.download-heading h1{max-width:52rem;margin:1rem 0 0;font-size:clamp(2.65rem,4.6vw,4.5rem);font-weight:650;line-height:1.08;letter-spacing:-.055em}.download-heading h1 em{font-style:normal;color:inherit}.download-heading>p{max-width:40rem;margin:1.4rem 0 0;color:var(--ink-600);font-size:1.05rem;line-height:1.75}
.install-workspace{display:grid;grid-template-columns:minmax(0,1fr);overflow:hidden;border:1px solid var(--glass-edge);border-radius:1.15rem;background:var(--glass-card);box-shadow:var(--glass-inset),var(--glass-shadow);scroll-margin-top:6rem}
.install-config{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,.9fr);align-items:start;gap:2rem;min-width:0;padding:1.75rem 2rem;border-bottom:1px solid var(--border);background:#f6faff80}.install-config__label{display:block;margin-bottom:.7rem;color:var(--ink-600);font-size:.9375rem;font-weight:550}
.platform-options{display:flex;gap:.4rem}.platform-options button{display:flex;flex:1;align-items:center;gap:.6rem;min-height:2.9rem;padding:.7rem .8rem;border:1px solid var(--border);border-radius:.65rem;background:#ffffff80;cursor:pointer;text-align:left;font-size:.9375rem}.platform-options button>svg{width:1.1rem;height:1.1rem;flex:none}.platform-options button>svg:last-child:not(:first-child){margin-left:auto;width:.85rem;color:var(--mint-700)}.platform-options button[aria-pressed=true]{border-color:#91baf0;background:linear-gradient(#fff,#edf5ff);box-shadow:var(--glass-inset);color:var(--mint-700)}
.channel-options{display:flex;gap:.2rem;padding:.2rem;border:1px solid var(--border);border-radius:.7rem;background:#ecf2fa}.channel-options button{flex:1;min-width:0;min-height:2.5rem;padding:.5rem .6rem;border:1px solid transparent;border-radius:.5rem;background:transparent;color:var(--ink-600);cursor:pointer;font-size:.9375rem}.channel-options button[aria-pressed=true]{border-color:#d9e6f5;background:#fff;color:var(--mint-700);box-shadow:var(--shadow-xs)}.install-config p{margin:.7rem 0 0;color:var(--ink-500);font-size:1rem;line-height:1.6}
.install-config dl{display:grid;gap:1rem;margin:0;padding:0 0 0 1.5rem;border-left:1px solid var(--border)}.install-config dt{font-size:.9375rem;color:var(--ink-500)}.install-config dd{margin:.35rem 0 0;font-family:var(--font-mono);font-size:.9375rem;overflow-wrap:anywhere}.install-config__status{display:flex;grid-column:1/-1;align-items:center;gap:.5rem;margin-top:-.75rem;color:var(--mint-700);font-size:.9375rem}.install-config__status svg{width:.9rem;flex:none}
.install-content{min-width:0;padding:clamp(1.25rem,3vw,2.25rem)}.install-content__heading{margin-bottom:2rem}.install-content h2{margin:.7rem 0 0;font-size:1.7rem;font-weight:600;letter-spacing:-.04em}.install-content__heading p{max-width:42rem;margin:.8rem 0 0;color:var(--ink-600);font-size:.95rem;line-height:1.75}.install-content__note{max-width:46rem;margin:1.5rem 0;color:var(--ink-500);font-size:.9375rem;line-height:1.75}
.portable-download{padding-top:1rem;border-top:1px solid var(--border)}.portable-download summary{min-height:2.75rem;align-content:center;cursor:pointer;font-size:.9375rem;font-weight:500}.portable-download p{font-size:1rem;line-height:1.75;color:var(--ink-600)}.portable-download :deep(.ui-button){margin-top:.5rem}
.windows-install{max-width:44rem}.windows-install__visual{display:flex;align-items:center;gap:1rem;margin-bottom:2rem;padding:1.4rem;border:1px solid var(--border);border-radius:1rem;background:#fff}.windows-install__visual img{width:4rem;height:4rem;object-fit:contain}.windows-install__visual span{color:var(--ink-900);font-size:1.2rem;font-weight:600;letter-spacing:-.035em}.windows-install h2 span{font-family:var(--font-mono);font-size:.9375rem;color:var(--ink-500)}.windows-install>p{max-width:34rem;margin:1rem 0 1.5rem;font-size:1rem;line-height:1.75;color:var(--ink-600)}.windows-install__dev{display:flex;gap:.7rem;align-items:start;margin-bottom:1.5rem;padding:1rem;background:#fffaf2;border:1px solid #eddcbe;border-radius:.75rem;font-size:.9375rem;line-height:1.75}.windows-install__dev svg{width:1.1rem;flex:none;margin-top:.2rem}
.after-install__heading{display:flex;align-items:center;justify-content:space-between;gap:1.5rem}.after-install h2{margin:0;font-size:2rem;font-weight:600;letter-spacing:-.04em}.after-install ol{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:2.5rem;margin:2rem 0 0;padding:0;list-style:none}.after-install li{padding-top:1.5rem;border-top:1px solid var(--border)}.after-install li>span{font-family:var(--font-mono);font-size:.9375rem;color:var(--mint-700)}.after-install h3{margin:.9rem 0 0;font-size:1.05rem;font-weight:550;letter-spacing:-.025em}.after-install p{max-width:23rem;margin:.8rem 0 0;font-size:1rem;line-height:1.8;color:var(--ink-600)}
@media(max-width:950px){.install-config{grid-template-columns:1fr 1fr;gap:1.5rem;padding:1.4rem}.install-config dl{display:flex;gap:2rem;grid-column:1/-1;padding:1rem 0 0;border-left:0;border-top:1px solid var(--border)}.install-config__status{margin-top:0}}
@media(max-width:620px){.download-heading{padding-block:2.75rem}.download-heading h1{font-size:clamp(2.4rem,9vw,3.5rem)}.download-heading>p{font-size:1rem}.install-config{grid-template-columns:1fr;padding:1.1rem;gap:1.4rem}.install-config dl,.install-config__status{grid-column:auto}.install-config dl{flex-wrap:wrap;gap:1rem 2rem}.install-content{padding:1.1rem}.install-content h2{font-size:1.5rem}.after-install__heading{align-items:start;flex-direction:column}.after-install ol{grid-template-columns:1fr;gap:1.4rem}.after-install p{max-width:none}.platform-options button,.channel-options button{min-height:2.75rem}}
</style>
