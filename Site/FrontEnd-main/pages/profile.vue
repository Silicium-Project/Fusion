<template>
  <div class="bg-[#131419] text-white min-h-screen p-8">
    <div class="max-w-7xl mx-auto">
      <NuxtLink to="/dashboard" class="flex items-center text-white/50 hover:text-white mb-8">
        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path></svg>
        Retour au tableau de bord
      </NuxtLink>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <!-- Left Column: User Card -->
        <div class="lg:col-span-1 bg-[#1f2029] rounded-2xl p-8 flex flex-col items-center">
          <div class="w-32 h-32 rounded-full bg-gradient-to-r from-purple-400 to-blue-400 flex items-center justify-center font-bold text-5xl mb-6">
            {{ user ? (user.username || user.email)?.[0].toUpperCase() : '' }}
          </div>
          <h2 class="text-3xl font-bold">{{ user?.firstName && user?.lastName ? `${user.firstName} ${user.lastName}` : (user?.username || user?.email) }}</h2>
          <p class="text-white/50 mt-2">{{ user?.email }}</p>
          <div class="mt-4 w-full text-center p-4 bg-black/20 rounded-lg">
            <p class="text-white/50 text-sm">Adresse du portefeuille</p>
            <p class="font-mono text-sm break-all">{{ user?.walletAddress || 'Non connectée' }}</p>
          </div>
          <div class="w-full mt-4">
            <button @click="connectWallet" :disabled="!!user?.walletAddress" class="w-full h-12 rounded-lg bg-purple-500/20 text-purple-400 font-bold hover:bg-purple-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
              {{ user?.walletAddress ? 'Portefeuille connecté' : 'Connecter le portefeuille Phantom' }}
            </button>
          </div>
          <div class="w-full mt-auto pt-8">
            <button @click="logout" class="w-full h-12 rounded-lg bg-red-500/20 text-red-400 font-bold hover:bg-red-500/40 transition-colors">
              Déconnexion
            </button>
          </div>
        </div>

        <!-- Right Column: Settings -->
        <div class="lg:col-span-2 bg-[#1f2029] rounded-2xl p-8">
          <div class="border-b border-white/10 mb-6">
            <nav class="-mb-px flex space-x-8">
              <button @click="activeTab = 'account'" :class="['whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm', activeTab === 'account' ? 'border-purple-400 text-purple-400' : 'border-transparent text-white/50 hover:text-white hover:border-white/30']">
                Compte
              </button>
              <button @click="activeTab = 'security'" :class="['whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm', activeTab === 'security' ? 'border-purple-400 text-purple-400' : 'border-transparent text-white/50 hover:text-white hover:border-white/30']">
                Sécurité
              </button>
            </nav>
          </div>

          <!-- Account Tab -->
          <div v-if="activeTab === 'account'">
            <form @submit.prevent="handleUpdateProfile" class="space-y-6">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label for="firstName" class="block text-sm font-medium text-white/80 mb-2">Prénom</label>
                  <input type="text" id="firstName" v-model="form.firstName" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
                </div>
                <div>
                  <label for="lastName" class="block text-sm font-medium text-white/80 mb-2">Nom de famille</label>
                  <input type="text" id="lastName" v-model="form.lastName" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
                </div>
              </div>
              <div>
                <label for="username" class="block text-sm font-medium text-white/80 mb-2">Nom d'utilisateur</label>
                <input type="text" id="username" v-model="form.username" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
              </div>
              <div>
                <label for="email" class="block text-sm font-medium text-white/80 mb-2">Adresse e-mail</label>
                <input type="email" id="email" :value="user?.email" disabled class="w-full h-12 bg-black/40 rounded-lg px-4 text-white/50 cursor-not-allowed">
              </div>
              <div class="pt-4">
                <button type="submit" class="w-full md:w-auto h-12 px-8 rounded-lg bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
                  Enregistrer les modifications
                </button>
              </div>
            </form>
          </div>

          <!-- Security Tab -->
          <div v-if="activeTab === 'security'">
            <form @submit.prevent="handleChangePassword" class="space-y-6">
              <div>
                <label for="currentPassword" class="block text-sm font-medium text-white/80 mb-2">Mot de passe actuel</label>
                <input type="password" id="currentPassword" v-model="passwordForm.currentPassword" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
              </div>
              <div>
                <label for="newPassword" class="block text-sm font-medium text-white/80 mb-2">Nouveau mot de passe</label>
                <input type="password" id="newPassword" v-model="passwordForm.newPassword" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
              </div>
              <div>
                <label for="confirmPassword" class="block text-sm font-medium text-white/80 mb-2">Confirmer le nouveau mot de passe</label>
                <input type="password" id="confirmPassword" v-model="passwordForm.confirmPassword" class="w-full h-12 bg-black/20 rounded-lg px-4 text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-purple-400">
              </div>
              <div class="pt-4">
                <button type="submit" class="w-full md:w-auto h-12 px-8 rounded-lg bg-gradient-to-r from-purple-400 to-blue-400 text-white font-bold text-lg hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
                  Changer le mot de passe
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import Cookies from 'js-cookie';
import { useRouter } from '#vue-router';
import * as web3 from '@solana/web3.js';

const user = ref(null);
const config = useRuntimeConfig();
const apiBase = config.public.apiBase;
const activeTab = ref('account');
const router = useRouter();

const form = reactive({
  firstName: '',
  lastName: '',
  username: '',
});

const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
});

const connectWallet = async () => {
  if (window.solana) {
    try {
      const resp = await window.solana.connect();
      const publicKey = resp.publicKey.toString();
      
      const token = Cookies.get('auth_token');
      if (!token) return;

      await $fetch(`${apiBase}/user/wallet`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: { walletAddress: publicKey }
      });
      
      if (user.value) {
        user.value.walletAddress = publicKey;
      }
      alert('Portefeuille connecté avec succès !');

    } catch (err) {
      console.error("Failed to connect wallet:", err);
      alert('Échec de la connexion du portefeuille.');
    }
  } else {
    alert('Portefeuille Phantom introuvable. Veuillez l\'installer.');
  }
};

const handleUpdateProfile = async () => {
  const token = Cookies.get('auth_token');
  if (!token) return;

  try {
    const updatedUser = await $fetch(`${apiBase}/user`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${token}` },
      body: {
        firstName: form.firstName,
        lastName: form.lastName,
        username: form.username,
      }
    });
    user.value = updatedUser;
    alert('Profil mis à jour avec succès !');
  } catch (error) {
    console.error("Failed to update profile:", error);
    alert('Échec de la mise à jour du profil.');
  }
};

const handleChangePassword = async () => {
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    alert("Les nouveaux mots de passe ne correspondent pas.");
    return;
  }
  const token = Cookies.get('auth_token');
  if (!token) return;

  try {
    await $fetch(`${apiBase}/user/password`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${token}` },
      body: {
        currentPassword: passwordForm.currentPassword,
        newPassword: passwordForm.newPassword,
      }
    });
    alert('Mot de passe mis à jour avec succès !');
    // Clear password fields
    passwordForm.currentPassword = '';
    passwordForm.newPassword = '';
    passwordForm.confirmPassword = '';
  } catch (error) {
    console.error("Failed to change password:", error);
    alert('Échec de la modification du mot de passe. Vérifiez votre mot de passe actuel.');
  }
};

const logout = () => {
  Cookies.remove('auth_token');
  router.push('/auth');
};

onMounted(async () => {
  const token = Cookies.get('auth_token');
  if (token) {
    try {
      const fetchedUser = await $fetch(`${apiBase}/user`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      user.value = fetchedUser;
      // Populate form with fetched data
      form.firstName = fetchedUser.firstName || '';
      form.lastName = fetchedUser.lastName || '';
      form.username = fetchedUser.username || '';
    } catch (error) {
      console.error("Failed to fetch user data:", error);
    }
  }
});
</script>
