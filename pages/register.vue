<template>
  <h1 class="flex justify-center font-extrabold text-white text-5xl mt-10">Silicium</h1>
  <div class="flex items-center justify-center h-screen bg-[#131419] space-x-44">
    <!-- Card Container -->
    <div class="w-[30rem] h-[45rem] bg-gradient-to-bl from-purple-400/15 to-blue-400/15 p-6 rounded-[20px] shadow-lg">
      <!-- Bienvenue -->
      <div class="text-center font-extrabold text-4xl md:text-4xl sm:text-4xl mt-28 sm:mt-34 md:mt-46 mx-auto max-w-md md:max-w-7xl">
        <p>
          <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Welcome !</span>
        </p>
      </div>
      <!-- Form -->
      <form @submit.prevent="loginSubmit" class="mt-12 w-11/12 mx-auto text-white text-xl flex flex-col items-center">
        <!-- Username field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="text"
              placeholder="Username or Email"
              v-model="loginForm.login"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Password Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="password"
              placeholder="Password"
              v-model="loginForm.password"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Submit -->
        <button type=submit class="flex items-center px-6 py-3 text-xl mt-12 font-bold rounded-full bg-gradient-to-br from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
          <span>Login</span>
        </button>
      </form>
      <!-- Forgot password text -->
      <div class="text-center font-bold text-white/50 text-base md:text-base sm:text-sm mx-auto max-w-md md:max-w-7xl mt-3">
        <p>
          Forgot Password
          <span class="text-transparent bg-blue-400 bg-clip-text">Click here</span>
        </p>
      </div>
    </div>
    <div class="w-[30rem] h-[45rem] bg-gradient-to-bl from-purple-400/15 to-blue-400/15 text-white p-6 rounded-[20px] shadow-lg">
      <!-- S'inscrire -->
      <div class="text-center font-extrabold text-4xl md:text-4xl sm:text-4xl mt-1 mx-auto max-w-md md:max-w-7xl">
        <p>
          <span class="text-transparent bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text">Sign Up</span>
        </p>
      </div>
      <!-- Form -->
      <form @submit.prevent="registerSubmit" class="mt-12 w-11/12 mx-auto text-white text-xl flex flex-col items-center">
        <!-- Username Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="text"
              placeholder="Username"
              v-model="registerForm.username"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- First Name Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="text"
              placeholder="First Name"
              v-model="registerForm.first_name"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Last Name Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="text"
              placeholder="Last Name"
              v-model="registerForm.last_name"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Email Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="text"
              placeholder="Email"
              v-model="registerForm.email"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Phone Number Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="text"
              placeholder="Phone Number"
              v-model="registerForm.phone_number"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Password Field -->
        <div class="w-full h-14 bg-black p-6 rounded-[10px] shadow-lg border-2 border-[#404040] mb-4 flex items-center">
          <input
              type="password"
              placeholder="Password"
              v-model="registerForm.password"
              class="bg-transparent text-white text-xl outline-none placeholder-white/20"
          />
        </div>
        <!-- Submit Field -->
        <button type=submit class="flex items-center px-6 py-3 text-xl mt-12 font-bold rounded-full bg-gradient-to-br from-purple-400 to-blue-400 hover:from-purple-500 hover:to-blue-500 transition-shadow shadow-lg">
          <span>Créer le compte</span>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import Cookies from 'js-cookie';
import {jwtDecode} from "jwt-decode";
import {useRouter} from "#vue-router";

const router = useRouter();

let loginForm = {
  login: '',
  password: '',
};

let registerForm = {
  username: '',
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  phone_number: '',
};

let loginResponse = {
  token: '',
}

let registerResponse = {
  ok: '',
}

const loginSubmit = async () => {
  try {
    loginResponse = await $fetch(`http://185.157.245.42:8080/login/`, {
      method: 'POST',
      body: loginForm
    });

    Cookies.set('auth_token', loginResponse.token, {
      expires: 7,
      sameSite: 'Strict',
    });

    const decodedToken = jwtDecode(loginResponse.token) as { role: string };

    if (decodedToken.role === 'admin') {
      await router.push('/admin/users');
    } else if (decodedToken.role === 'user') {
      await router.push('/dashboard');
    }
  } catch (error) {
    console.error(error);
  }
}

const registerSubmit = async () => {
  try {
    registerResponse = await $fetch(`http://185.157.245.42:8080/register/`, {
      method: 'POST',
      body: registerForm
    });
  } catch (error) {
    console.error(error);
  }
}
</script>

<style>
html,
body {
  background-color: #131419;
  margin: 0;
}
</style>