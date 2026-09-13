<template>
  <header class="public-header">
    <div class="public-header__inner marketing-container">
      <BrandLogo />
      <nav class="public-header__nav" aria-label="Navigation principale">
        <NuxtLink v-for="item in navigation" :key="item.to" :to="item.to" :class="{ 'is-active': isCurrent(item) }"><span>{{ item.index }}</span>{{ item.label }}</NuxtLink>
      </nav>
      <div class="public-header__actions">
        <ReleaseBadge :channel="releaseChannel" :version="releaseVersion" :build="releaseBuild" />
        <UiButton v-if="isAuthenticated" to="/dashboard" variant="ghost" size="small">Ouvrir l’espace</UiButton>
        <UiButton v-if="isAuthenticated" to="/profile" variant="secondary" size="small" icon="account">{{ displayName }}</UiButton>
        <template v-else>
          <UiButton to="/auth?mode=login" variant="ghost" size="small">Se connecter</UiButton>
          <UiButton to="/auth?mode=register" size="small">Ouvrir un compte</UiButton>
        </template>
      </div>
      <button class="public-header__menu" type="button" :aria-label="menuOpen ? 'Fermer le menu' : 'Ouvrir le menu'" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
        <UiIcon :name="menuOpen ? 'x' : 'menu'" />
      </button>
    </div>
    <nav v-if="menuOpen" class="public-header__mobile" aria-label="Navigation mobile">
      <NuxtLink v-for="item in navigation" :key="item.to" :to="item.to"><span><small>{{ item.index }}</small>{{ item.label }}</span><UiIcon name="chevron" /></NuxtLink>
      <div class="public-header__mobile-actions">
        <UiButton v-if="isAuthenticated" to="/dashboard">Ouvrir l’espace</UiButton>
        <UiButton v-if="isAuthenticated" to="/profile" variant="secondary">{{ displayName }}</UiButton>
        <template v-else><UiButton to="/auth?mode=login" variant="secondary">Se connecter</UiButton><UiButton to="/auth?mode=register">Ouvrir un compte</UiButton></template>
      </div>
    </nav>
  </header>
</template>

<script setup lang="ts">
const route = useRoute();
const menuOpen = ref(false);
const config = useRuntimeConfig();
const releaseChannel = String(config.public.releaseChannel || 'dev');
const releaseVersion = String(config.public.releaseVersion || 'unknown');
const releaseBuild = String(config.public.releaseBuild || 'local');
const { isAuthenticated, displayName, loadUser } = useSession();
const navigation = [
  { index: '01', label: 'Produit', to: '/service' },
  { index: '02', label: 'Télécharger', to: '/download' },
  { index: '03', label: 'Réseau', to: '/about#network' },
  { index: '04', label: 'Blockchain', to: '/blockchain' },
  { index: '05', label: 'À propos', to: '/about' },
  { index: '06', label: 'Idées', to: '/contact' },
];
function isCurrent(item: { to: string }) {
  const target = new URL(item.to, 'http://silicium.local');
  if (target.pathname !== route.path) return false;
  const currentHash = route.hash || (import.meta.client ? window.location.hash : '');
  return target.hash ? target.hash === currentHash : !currentHash;
}
watch(() => route.fullPath, () => { menuOpen.value = false; });
onMounted(() => { if (isAuthenticated.value) loadUser().catch(() => undefined); });
</script>

<style scoped>
.public-header{position:sticky;top:0;z-index:50;border-bottom:1px solid rgba(21,40,61,.08);background:rgba(248,248,245,.7);-webkit-backdrop-filter:blur(22px) saturate(1.2);backdrop-filter:blur(22px) saturate(1.2)}
.public-header__inner{display:grid;min-height:5rem;grid-template-columns:auto 1fr auto;align-items:center;gap:2rem}
.public-header__nav{display:flex;justify-content:center;gap:1.7rem;color:var(--ink-600);font-size:.75rem;font-weight:730}
.public-header__nav a{position:relative;display:inline-flex;align-items:center;gap:.42rem;padding-block:1.9rem;transition:color .2s ease}
.public-header__nav a span{color:var(--ink-400);font-family:var(--font-mono);font-size:.58rem;font-weight:500;letter-spacing:.02em}
.public-header__nav a:hover,.public-header__nav a.is-active{color:var(--ink-900)}
.public-header__nav a::after{position:absolute;right:0;bottom:0;left:0;height:2px;transform:scaleX(0);border-radius:9px;background:var(--mint-500);content:'';transition:transform .25s var(--ease-out)}
.public-header__nav a.is-active::after{transform:scaleX(1)}
.public-header__actions{display:flex;align-items:center;gap:.35rem}.public-header__actions :deep(.release-badge){margin-right:.3rem}
.public-header__menu{display:none;width:2.6rem;height:2.6rem;place-items:center;border:1px solid var(--border);border-radius:.75rem;background:rgba(255,255,255,.6);cursor:pointer}
.public-header__menu svg{width:1.05rem}
.public-header__mobile{display:none;width:min(calc(100% - 2rem),1240px);margin:.7rem auto 1rem;padding:.65rem;border:1px solid var(--glass-edge);border-radius:1.25rem;background:var(--glass-solid);box-shadow:var(--glass-inset),var(--glass-shadow);-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px)}
.public-header__mobile>a{display:flex;align-items:center;justify-content:space-between;padding:.95rem .7rem;border-bottom:1px solid var(--border);font-size:.87rem;font-weight:730}
.public-header__mobile>a span{display:flex;align-items:center;gap:.75rem}.public-header__mobile>a small{color:var(--ink-400);font-family:var(--font-mono);font-size:.58rem;font-weight:500}.public-header__mobile>a svg{width:.9rem;color:var(--ink-500)}
.public-header__mobile-actions{display:grid;grid-template-columns:1fr 1fr;gap:.55rem;padding:.9rem .25rem .15rem}
@media(max-width:900px){.public-header__inner{min-height:4.35rem}.public-header__nav,.public-header__actions{display:none}.public-header__menu{display:grid}.public-header__mobile{display:block}}
@media(max-width:520px){.public-header__mobile{width:calc(100% - 1.5rem)}.public-header__mobile-actions{grid-template-columns:1fr}.public-header__inner{min-height:4.1rem}}
</style>
