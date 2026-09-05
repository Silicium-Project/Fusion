<template>
  <header class="fixed inset-x-0 top-0 z-50 px-4 pt-4 sm:px-6">
    <nav
      class="mx-auto flex h-16 max-w-7xl items-center justify-between rounded-2xl border border-white/10 bg-[#0a0c12]/80 px-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)] backdrop-blur-xl sm:px-5"
      aria-label="Navigation principale"
    >
      <NuxtLink to="/" class="group flex items-center gap-3" aria-label="Silicium" @click="closeMenu">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
        <span class="text-[1.05rem] font-extrabold tracking-[-0.03em] text-white">Silicium</span>
      </NuxtLink>

      <div class="hidden items-center gap-1 md:flex">
        <NuxtLink v-if="isConnected" to="/dashboard" class="nav-link" active-class="nav-link-active">Dashboard</NuxtLink>
        <NuxtLink to="/about" class="nav-link" active-class="nav-link-active">À propos</NuxtLink>
        <NuxtLink to="/service" class="nav-link" active-class="nav-link-active">Service</NuxtLink>
        <NuxtLink to="/contact" class="nav-link" active-class="nav-link-active">Contact</NuxtLink>
      </div>

      <div class="hidden items-center gap-2 md:flex">
        <span v-if="hasStatus" class="mr-2 inline-flex items-center gap-2 text-xs font-semibold text-white/55">
          <span class="h-1.5 w-1.5 rounded-full" :class="statusDotClass"></span>{{ statusLabel }}
        </span>
        <NuxtLink v-if="isConnected" to="/profile" title="Mon profil" class="profile-link">
          <span class="profile-avatar" aria-hidden="true">{{ userInitial }}</span>
          <span class="max-w-36 truncate">{{ userName }}</span>
        </NuxtLink>
        <template v-else>
          <button type="button" class="rounded-xl px-4 py-2.5 text-sm font-semibold text-white/70 transition hover:bg-white/5 hover:text-white" @click="handleSignIn">Se connecter</button>
          <button type="button" class="rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-[#090b10] transition hover:bg-[#d9ff9d]" @click="handleSignUp">S'inscrire</button>
        </template>
      </div>

      <button
        type="button"
        class="grid h-10 w-10 place-items-center rounded-xl border border-white/10 text-white md:hidden"
        :aria-expanded="menuOpen"
        aria-controls="mobile-navigation"
        :aria-label="menuOpen ? 'Fermer le menu' : 'Ouvrir le menu'"
        @click="menuOpen = !menuOpen"
      >
        <svg v-if="!menuOpen" viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round" /></svg>
        <svg v-else viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke-linecap="round" /></svg>
      </button>
    </nav>

    <div v-if="menuOpen" id="mobile-navigation" role="navigation" aria-label="Navigation mobile" class="mx-auto mt-2 max-w-7xl rounded-2xl border border-white/10 bg-[#0a0c12]/95 p-3 shadow-2xl backdrop-blur-xl md:hidden">
      <NuxtLink v-if="isConnected" to="/dashboard" class="mobile-link" @click="closeMenu">Dashboard</NuxtLink>
      <NuxtLink to="/about" class="mobile-link" @click="closeMenu">À propos</NuxtLink>
      <NuxtLink to="/service" class="mobile-link" @click="closeMenu">Service</NuxtLink>
      <NuxtLink to="/contact" class="mobile-link" @click="closeMenu">Contact</NuxtLink>
      <div class="mt-2 grid grid-cols-2 gap-2 border-t border-white/10 pt-3">
        <NuxtLink v-if="isConnected" to="/profile" class="col-span-2 flex items-center justify-center gap-2 rounded-xl bg-white px-3 py-3 text-sm font-bold text-[#090b10]" @click="closeMenu"><span class="profile-avatar" aria-hidden="true">{{ userInitial }}</span>{{ userName }}</NuxtLink>
        <template v-else>
          <button type="button" class="rounded-xl border border-white/10 px-3 py-3 text-center text-sm font-semibold text-white" @click="handleSignIn">Se connecter</button>
          <button type="button" class="rounded-xl bg-white px-3 py-3 text-center text-sm font-bold text-[#090b10]" @click="handleSignUp">S'inscrire</button>
        </template>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import Cookies from 'js-cookie';
import { tokenExpiry } from '../utils/auth';

type ServiceStatus = 'up' | 'down' | 'loading';

const props = defineProps<{ status?: ServiceStatus }>();
const route = useRoute();
const menuOpen = ref(false);
const isConnected = ref(false);
const apiBase = useRuntimeConfig().public.apiBase;
const user = ref<{ username?: string; email: string } | null>(null);
const userName = computed(() => user.value?.username || user.value?.email || 'Mon profil');
const userInitial = computed(() => user.value ? Array.from(userName.value)[0]?.toUpperCase() : '?');
const hasStatus = computed(() => props.status !== undefined);
const statusLabel = computed(() => props.status === 'up' ? 'Services opérationnels' : props.status === 'down' ? 'Incident détecté' : 'Vérification en cours');
const statusDotClass = computed(() => props.status === 'up' ? 'bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.7)]' : props.status === 'down' ? 'bg-rose-400 shadow-[0_0_12px_rgba(251,113,133,0.7)]' : 'animate-pulse bg-amber-300');
let expiryTimer: ReturnType<typeof setTimeout> | undefined;
let loadedToken: string | undefined;
let userRequest: AbortController | undefined;

async function loadUser(token: string) {
  userRequest?.abort();
  const controller = new AbortController();
  userRequest = controller;
  user.value = null;
  try {
    const profile = await $fetch<{ username?: string; email: string }>(`${apiBase}/user`, {
      headers: { Authorization: `Bearer ${token}` }, retry: 0, timeout: 10_000, signal: controller.signal,
    });
    if (!controller.signal.aborted && Cookies.get('auth_token') === token) user.value = profile;
  } catch {
    if (!controller.signal.aborted) loadedToken = undefined;
  }
}

function syncSession() {
  if (expiryTimer) clearTimeout(expiryTimer);
  const token = Cookies.get('auth_token');
  const expires = tokenExpiry(token);
  isConnected.value = !!expires;
  if (!expires) {
    if (token) Cookies.remove('auth_token', { path: '/' });
    userRequest?.abort();
    user.value = null;
    loadedToken = undefined;
    return;
  }
  if (token && token !== loadedToken) {
    loadedToken = token;
    void loadUser(token);
  }
  expiryTimer = setTimeout(syncSession, Math.min(expires.getTime() - Date.now() + 50, 2_147_483_647));
}

function closeMenu() { menuOpen.value = false; }
function handleSignIn() { closeMenu(); void navigateTo({ path: '/auth', query: { mode: 'login' } }); }
function handleSignUp() { closeMenu(); void navigateTo({ path: '/auth', query: { mode: 'register' } }); }

watch(() => route.fullPath, closeMenu);
onMounted(() => { syncSession(); window.addEventListener('focus', syncSession); });
onUnmounted(() => {
  userRequest?.abort();
  if (expiryTimer) clearTimeout(expiryTimer);
  window.removeEventListener('focus', syncSession);
});
</script>

<style scoped>
.brand-mark{display:grid;width:2rem;height:2rem;grid-template-columns:repeat(2,.48rem);grid-template-rows:repeat(2,.48rem);place-content:center;gap:.2rem;border:1px solid rgba(255,255,255,.16);border-radius:.7rem;background:linear-gradient(145deg,rgba(145,128,255,.3),rgba(94,234,212,.08));box-shadow:inset 0 1px 0 rgba(255,255,255,.12)}.brand-mark span{border-radius:.12rem;background:#a89cff;transition:transform 180ms ease}.brand-mark span:nth-child(2),.brand-mark span:nth-child(3){background:#67e8d4}.group:hover .brand-mark span{transform:scale(.78)}
.nav-link,.mobile-link{color:rgba(255,255,255,.58);font-size:.875rem;font-weight:650;transition:color 160ms ease,background-color 160ms ease}.nav-link{border-radius:.75rem;padding:.65rem .9rem}.nav-link:hover,.nav-link-active,.mobile-link:hover{color:#fff;background:rgba(255,255,255,.05)}.mobile-link{display:block;border-radius:.75rem;padding:.85rem .9rem}.profile-link{display:flex;min-width:0;align-items:center;gap:.6rem;border:1px solid rgba(255,255,255,.09);border-radius:.75rem;background:rgba(255,255,255,.035);padding:.35rem .65rem .35rem .35rem;color:rgba(255,255,255,.75);font-size:.8rem;font-weight:700;transition:background-color 160ms ease,color 160ms ease}.profile-link:hover{background:rgba(255,255,255,.07);color:#fff}.profile-avatar{display:grid;width:1.8rem;height:1.8rem;flex:none;place-items:center;border-radius:.55rem;background:linear-gradient(135deg,#9b8cff,#69e7d3);color:#090b10;font-size:.72rem;font-weight:900}
</style>
