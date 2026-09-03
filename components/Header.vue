<template>
  <header class="fixed top-0 left-0 z-50 flex w-full flex-wrap items-center gap-x-6 gap-y-4 border-b border-white/5 bg-[#070912]/95 px-6 py-5 text-white backdrop-blur md:flex-nowrap md:py-6">
    <NuxtLink to="/" class="text-xl font-extrabold">Silicium</NuxtLink>
    <nav aria-label="Navigation principale" class="order-3 flex w-full items-center gap-6 overflow-x-auto pb-1 text-base md:order-none md:w-auto md:gap-8 md:text-xl">
      <NuxtLink v-if="isConnected" to="/dashboard" class="hover-gradient-underline whitespace-nowrap" active-class="text-purple-300">Dashboard</NuxtLink>
      <NuxtLink to="/about" class="hover-gradient-underline whitespace-nowrap" active-class="text-purple-300">À propos</NuxtLink>
      <NuxtLink to="/service" class="hover-gradient-underline" active-class="text-purple-300">Service</NuxtLink>
      <NuxtLink to="/contact" class="hover-gradient-underline" active-class="text-purple-300">Contact</NuxtLink>
    </nav>
    <NuxtLink v-if="isConnected" to="/profile" title="Mon profil" class="ml-auto flex min-w-0 items-center gap-3 rounded-lg bg-black/20 p-2 transition-colors hover:bg-black/30">
      <span aria-hidden="true" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-purple-400 to-blue-400 text-xl font-bold">{{ userInitial }}</span>
      <span class="max-w-28 truncate pr-2 font-semibold lg:max-w-48">{{ userName }}</span>
    </NuxtLink>
    <div v-else class="ml-auto flex items-center gap-2 sm:gap-3">
      <button @click="handleSignIn" class="rounded-full border border-white/40 px-3 py-2 text-sm font-bold hover:bg-white/10 lg:px-5 lg:py-3">Se connecter</button>
      <button @click="handleSignUp" class="rounded-full bg-gradient-to-r from-purple-400 to-blue-400 px-3 py-2 text-sm font-bold lg:px-5 lg:py-3">S'inscrire</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import Cookies from 'js-cookie';
import { tokenExpiry } from '../utils/auth';

const isConnected = ref(false);
const apiBase = useRuntimeConfig().public.apiBase;
const user = ref<{ username?: string; email: string } | null>(null);
const userName = computed(() => user.value?.username || user.value?.email || 'Mon profil');
const userInitial = computed(() => user.value ? Array.from(userName.value)[0]?.toUpperCase() : '?');
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
    // Keep the profile link usable; retry on focus if the API was unavailable.
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

onMounted(() => {
  syncSession();
  window.addEventListener('focus', syncSession);
});
onUnmounted(() => {
  userRequest?.abort();
  if (expiryTimer) clearTimeout(expiryTimer);
  window.removeEventListener('focus', syncSession);
});

const handleSignIn = () => {
  navigateTo({ path: '/auth', query: { mode: 'login' } });
};
const handleSignUp = () => {
  navigateTo({ path: '/auth', query: { mode: 'register' } });
};
</script>
