<template>
  <header class="public-header" @keydown.esc="closeMenu">
    <div class="public-header__inner marketing-container">
      <BrandLogo />
      <nav class="public-header__nav" :aria-label="t('nav.main')">
        <NuxtLink v-for="item in navigation" :key="item.to" :to="item.to" :aria-current="isCurrent(item.to) ? 'page' : undefined">{{ item.label }}</NuxtLink>
      </nav>
      <div class="public-header__utility">
        <LocaleSwitcher />
        <UiButton v-if="isAuthenticated" to="/dashboard" size="small" icon="arrow">{{ t('nav.openSpace') }}</UiButton>
        <template v-else><UiButton to="/auth?mode=login" variant="ghost" size="small">{{ t('nav.signIn') }}</UiButton><UiButton to="/jobs/new" size="small">{{ t('experience.home.start') }}</UiButton></template>
      </div>
      <button ref="menuButton" class="public-header__menu" type="button" :aria-label="menuOpen ? t('nav.closeMenu') : t('nav.openMenu')" :aria-expanded="menuOpen" aria-controls="public-mobile-navigation" @click="menuOpen = !menuOpen"><UiIcon :name="menuOpen ? 'x' : 'menu'" /></button>
    </div>
    <nav v-if="menuOpen" id="public-mobile-navigation" ref="mobileNav" class="public-header__mobile" :aria-label="t('nav.mobile')">
      <NuxtLink v-for="(item, index) in navigation" :key="item.to" :to="item.to"><span><small>0{{ index + 1 }}</small>{{ item.label }}</span><UiIcon name="arrow" /></NuxtLink>
      <div class="public-header__mobile-actions"><UiButton v-if="isAuthenticated" to="/dashboard">{{ t('nav.openSpace') }}</UiButton><template v-else><UiButton to="/auth?mode=login" variant="secondary">{{ t('nav.signIn') }}</UiButton><UiButton to="/jobs/new">{{ t('experience.home.start') }}</UiButton></template></div>
    </nav>
  </header>
</template>

<script setup lang="ts">
const { t } = useI18n();
const route = useRoute();
const menuOpen = ref(false);
const menuButton = ref<HTMLButtonElement | null>(null);
const mobileNav = ref<HTMLElement | null>(null);
const { isAuthenticated, loadUser } = useSession();
const navigation = computed(() => [
  { label: t('nav.product'), to: '/service' },
  { label: t('observability.worker.nav'), to: '/workers' },
  { label: t('experience.install'), to: '/download' },
  { label: t('nav.about'), to: '/about' },
  { label: t('experience.contact'), to: '/contact' },
]);
function isCurrent(to: string) { return route.path === to; }
function closeMenu() { if (menuOpen.value) { menuOpen.value = false; menuButton.value?.focus(); } }
watch(menuOpen, async (open) => { if (open) { await nextTick(); mobileNav.value?.querySelector('a')?.focus(); } });
watch(() => route.fullPath, () => { menuOpen.value = false; });
onMounted(() => { if (isAuthenticated.value) loadUser().catch(() => undefined); });
</script>

<style scoped>
.public-header{position:sticky;top:0;z-index:50;border-bottom:1px solid var(--border);background:rgba(255,255,255,.84);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px)}
.public-header__inner{display:flex;align-items:center;gap:1.5rem;min-height:5rem}
.public-header__nav{display:flex;align-items:center;justify-content:center;gap:1.45rem;margin-inline:auto;color:var(--ink-800);font-size:1rem;font-weight:500}
.public-header__nav a{position:relative;padding-block:1.85rem}.public-header__nav a:hover,.public-header__nav a[aria-current]{color:var(--mint-700)}.public-header__nav a[aria-current]::after{position:absolute;bottom:1.2rem;left:0;right:0;height:2px;border-radius:2px;background:var(--mint-500);content:''}
.public-header__utility{display:flex;align-items:center;gap:.4rem}.public-header__utility :deep(.ui-button){font-size:1rem}.public-header__utility :deep(.locale-switcher){margin-right:.5rem}
.public-header__menu{display:none;width:2.75rem;height:2.75rem;place-items:center;border:1px solid var(--border);border-radius:.65rem;background:var(--glass-clear);box-shadow:var(--glass-inset);cursor:pointer}.public-header__menu svg{width:1.1rem}
.public-header__mobile{width:min(calc(100% - 2.5rem),1160px);margin:0 auto 1rem;padding:1rem 1.25rem;border:1px solid var(--glass-edge);border-radius:1rem;background:rgba(255,255,255,.97);box-shadow:var(--shadow-md)}
.public-header__mobile>a{display:flex;justify-content:space-between;align-items:center;gap:1rem;min-height:3.4rem;border-bottom:1px solid var(--border);font-size:1rem}.public-header__mobile>a span{display:flex;gap:1rem;align-items:center}.public-header__mobile small{font-family:var(--font-mono);font-size:1rem;color:var(--ink-400)}.public-header__mobile>a svg{width:1rem;color:var(--mint-700)}.public-header__mobile-actions{display:flex;gap:.6rem;padding-top:1.25rem}.public-header__mobile-actions :deep(.ui-button){flex:1}
@media(min-width:1201px){.public-header__mobile{display:none}}
@media(max-width:1200px){.public-header__inner{gap:.75rem;min-height:4.5rem}.public-header__nav,.public-header__utility :deep(.ui-button){display:none}.public-header__utility{margin-left:auto}.public-header__menu{display:grid}}
@media(max-width:520px){.public-header__inner :deep(.brand-logo){gap:.55rem}.public-header__inner :deep(.brand-logo__name){font-size:1.1rem}.public-header__utility :deep(.locale-switcher){margin:0}.public-header__utility :deep(.locale-switcher button){min-width:1.7rem;font-size:1rem}.public-header__mobile{width:calc(100% - 2rem)}.public-header__mobile-actions{flex-direction:column}}
</style>
