export default defineNuxtConfig({
  runtimeConfig: {
    public: {
      contactEmail: process.env.NUXT_PUBLIC_CONTACT_EMAIL || '',
      adminToken: process.env.NUXT_PUBLIC_ADMIN_TOKEN || '',
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
      devnetDashboardUrl: process.env.NUXT_PUBLIC_DEVNET_DASHBOARD_URL || '/network/',
      updateManifestUrl: process.env.NUXT_PUBLIC_UPDATE_MANIFEST_URL || '/downloads/update-manifest.json',
      statusRefreshSeconds: process.env.NUXT_PUBLIC_STATUS_REFRESH_SECONDS || '30',
      nodeAppWindowsUrl: process.env.NUXT_PUBLIC_NODE_APP_WINDOWS_URL || '/downloads/silicium-node-windows.exe',
      nodeAppWindowsDevUrl: process.env.NUXT_PUBLIC_NODE_APP_WINDOWS_DEV_URL || '/downloads/silicium-node-windows-dev.exe',
      nodeAppLinuxDevUrl: process.env.NUXT_PUBLIC_NODE_APP_LINUX_DEV_URL || '/downloads/silicium-node-linux-dev.AppImage',
    },
  },
  app: {
    head: {
      title: 'Silicium — Calcul distribué',
      meta: [
        { name: 'description', content: 'Silicium coordonne vos machines, distribue vos calculs et centralise le suivi des résultats.' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'theme-color', content: '#080a0f' },
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap' }
      ],
    },
  },
  nitro: {
    routeRules: {
      '/': { headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } },
      '/auth': { headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } },
      '/dashboard': { headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } },
      '/downloads/update-manifest.json': { headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } },
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
    externals: {
      external: ['@solana/web3.js'],
    },
  },

  vite: {
    define: {
      'process.env': '{}',
      'global': 'globalThis',
    },
    optimizeDeps: {
      include: ['@solana/web3.js', 'buffer'],
      esbuildOptions: {
        define: {
          global: 'globalThis',
        },
      },
    },
    resolve: {
      alias: {
        buffer: 'buffer',
      },
    },
    ssr: {
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
