export default defineNuxtConfig({
  runtimeConfig: {
    public: {
      adminToken: process.env.NUXT_PUBLIC_ADMIN_TOKEN || '',
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
      devnetDashboardUrl: process.env.NUXT_PUBLIC_DEVNET_DASHBOARD_URL || '/network/',
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
    },
    // Exclude @solana/web3.js from Nitro SSR bundle - it's browser-only
    externals: {
      external: ['@solana/web3.js'],
    },
  },

  // @solana/web3.js v1.x requires Node built-ins polyfilled for browser
  vite: {
    define: {
      // polyfill process and global for @solana/web3.js
      'process.env': '{}',
      'global': 'globalThis',
    },
    optimizeDeps: {
      include: ['@solana/web3.js', 'buffer'],
      esbuildOptions: {
        // Node.js global to browser globalThis
        define: {
          global: 'globalThis',
        },
      },
    },
    resolve: {
      alias: {
        // polyfill buffer for browser
        buffer: 'buffer',
      },
    },
    ssr: {
      // Don't bundle @solana in SSR — it must only run in browser
      noExternal: [],
      external: ['@solana/web3.js'],
    },
  },

  css: [
    '@/assets/css/main.css'
  ],

  compatibilityDate: '2024-10-10',
  modules: ['@nuxtjs/tailwindcss'],
})
