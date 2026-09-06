<template>
  <header class="public-header">
    <div class="public-header__inner content-width">
      <BrandLogo />
      <nav class="public-header__nav" aria-label="Navigation principale">
        <NuxtLink v-for="item in navigation" :key="item.to" :to="item.to">{{ item.label }}</NuxtLink>
      </nav>
      <div class="public-header__actions">
        <UiButton v-if="isAuthenticated" to="/dashboard" variant="ghost" size="small">Dashboard</UiButton>
        <UiButton v-if="isAuthenticated" to="/profile" variant="secondary" size="small" icon="account">{{ displayName }}</UiButton>
        <template v-else>
          <UiButton to="/auth?mode=login" variant="ghost" size="small">Se connecter</UiButton>
          <UiButton to="/auth?mode=register" size="small">Créer un compte</UiButton>
        </template>
      </div>
      <button class="public-header__menu" type="button" :aria-label="menuOpen ? 'Fermer le menu' : 'Ouvrir le menu'" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
        <UiIcon :name="menuOpen ? 'x' : 'menu'" />
      </button>
    </div>
    <nav v-if="menuOpen" class="public-header__mobile" aria-label="Navigation mobile">
      <NuxtLink v-for="item in navigation" :key="item.to" :to="item.to">{{ item.label }}<UiIcon name="chevron" /></NuxtLink>
      <div class="public-header__mobile-actions">
        <UiButton v-if="isAuthenticated" to="/dashboard">Ouvrir le dashboard</UiButton>
        <UiButton v-if="isAuthenticated" to="/profile" variant="secondary">{{ displayName }}</UiButton>
        <template v-else><UiButton to="/auth?mode=login" variant="secondary">Se connecter</UiButton><UiButton to="/auth?mode=register">Créer un compte</UiButton></template>
      </div>
    </nav>
  </header>
</template>

<script setup lang="ts">
const route = useRoute();
const menuOpen = ref(false);
const { isAuthenticated, displayName, loadUser } = useSession();
const navigation = [
  { label: 'Produit', to: '/service' },
  { label: 'Réseau', to: '/about#network' },
  { label: 'À propos', to: '/about' },
  { label: 'Contact', to: '/contact' },
];
watch(() => route.fullPath, () => { menuOpen.value = false; });
onMounted(() => { if (isAuthenticated.value) loadUser().catch(() => undefined); });
</script>

<style scoped>
.public-header { position: sticky; top: 0; z-index: 50; border-bottom: 1px solid rgba(23,34,49,.09); background: rgba(248,247,243,.88); backdrop-filter: blur(18px) saturate(1.3); }
.public-header__inner { display: grid; min-height: 4.75rem; grid-template-columns: auto 1fr auto; align-items: center; gap: 2rem; }
.public-header__nav { display: flex; justify-content: center; gap: 1.85rem; color: var(--ink-600); font-size: .76rem; font-weight: 700; }
.public-header__nav a { position: relative; transition: color .15s ease; }.public-header__nav a:hover,.public-header__nav a.router-link-active{color:var(--ink-950)}
.public-header__nav a::after { position:absolute;right:0;bottom:-.55rem;left:0;height:2px;transform:scaleX(0);border-radius:9px;background:var(--mint-500);content:'';transition:transform .15s ease }.public-header__nav a.router-link-active::after{transform:scaleX(1)}
.public-header__actions { display: flex; align-items: center; gap: .35rem; }
.public-header__menu { display: none; width: 2.6rem; height: 2.6rem; place-items: center; border: 1px solid var(--border); border-radius: .7rem; background: white; cursor: pointer; }.public-header__menu svg{width:1.1rem}
.public-header__mobile { display: none; border-top: 1px solid var(--border); padding: .5rem .75rem 1rem; background: var(--paper-warm); }
.public-header__mobile > a { display:flex;align-items:center;justify-content:space-between;padding:.9rem .5rem;border-bottom:1px solid var(--border);font-size:.83rem;font-weight:750 }.public-header__mobile > a svg{width:.9rem;color:var(--ink-500)}
.public-header__mobile-actions { display:grid;grid-template-columns:1fr 1fr;gap:.55rem;padding-top:.85rem }
@media(max-width:900px){.public-header__inner{min-height:4.2rem;grid-template-columns:auto 1fr auto}.public-header__nav,.public-header__actions{display:none}.public-header__menu{display:grid}.public-header__mobile{display:block}}
</style>
