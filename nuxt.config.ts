export default defineNuxtConfig({
  runtimeConfig: {
    public: {
      adminToken: process.env.NUXT_PUBLIC_ADMIN_TOKEN || '',
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8080',
    },
  },
  app: {
    head: {
      title: 'Silicium',
      meta: [
        { name: 'description', content: 'Welcome to Silicium!' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,100;0,300;0,400;0,700;0,900;1,100;1,300;1,400;1,700;1,900&display=swap" rel="stylesheet' }
      ],
    },
  },
  nitro: {
    routeRules: {
      '/widget': {
        cors: true,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
          'Access-Control-Allow-Headers': 'Origin, Content-Type, Accept',
          'Access-Control-Allow-Credentials': 'true'
        }
      }
    }
  },

  css: [
    '@/assets/css/main.css'
  ],

  compatibilityDate: '2024-10-10',
  modules: ['@nuxtjs/tailwindcss'],
})