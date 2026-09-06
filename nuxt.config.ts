export default defineNuxtConfig({
  devtools: { enabled: false },

  runtimeConfig: {
    public: {
      contactEmail: process.env.NUXT_PUBLIC_CONTACT_EMAIL || '',
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
      devnetDashboardUrl: process.env.NUXT_PUBLIC_DEVNET_DASHBOARD_URL || '/network/',
      solanaRpc: process.env.NUXT_PUBLIC_SOLANA_RPC || 'https://api.devnet.solana.com',
      updateManifestUrl: process.env.NUXT_PUBLIC_UPDATE_MANIFEST_URL || '/downloads/update-manifest.json',
      statusRefreshSeconds: process.env.NUXT_PUBLIC_STATUS_REFRESH_SECONDS || '30',
      nodeAppWindowsUrl: process.env.NUXT_PUBLIC_NODE_APP_WINDOWS_URL || '/downloads/silicium-node-windows.exe',
      nodeAppWindowsDevUrl: process.env.NUXT_PUBLIC_NODE_APP_WINDOWS_DEV_URL || '/downloads/silicium-node-windows-dev.exe',
      nodeAppLinuxDevUrl: process.env.NUXT_PUBLIC_NODE_APP_LINUX_DEV_URL || '/downloads/silicium-node-linux-dev.AppImage',
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'fr' },
      title: 'Silicium — Calcul distribué',
      meta: [
        { name: 'description', content: 'Silicium coordonne vos machines, distribue vos calculs et centralise le suivi des résultats.' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#f4f5f1' },
        { name: 'color-scheme', content: 'light' },
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap' },
      ],
    },
  },

  css: ['@/assets/css/main.css'],
  components: [{ path: '~/components', pathPrefix: false }],

  nitro: {
    routeRules: {
      '/auth': { headers: { 'Cache-Control': 'no-store' } },
      '/dashboard': { headers: { 'Cache-Control': 'no-store' } },
      '/jobs/**': { headers: { 'Cache-Control': 'no-store' } },
      '/network': { headers: { 'Cache-Control': 'no-store' } },
      '/nodes': { headers: { 'Cache-Control': 'no-store' } },
      '/profile': { headers: { 'Cache-Control': 'no-store' } },
      '/downloads/update-manifest.json': { headers: { 'Cache-Control': 'no-cache, must-revalidate' } },
    },
    externals: { external: ['@solana/web3.js'] },
  },

  vite: {
    define: { 'process.env': '{}', global: 'globalThis' },
    optimizeDeps: {
      include: ['@solana/web3.js', 'buffer'],
      esbuildOptions: { define: { global: 'globalThis' } },
    },
    resolve: { alias: { buffer: 'buffer' } },
    ssr: { external: ['@solana/web3.js'] },
  },

  typescript: { typeCheck: true },
  compatibilityDate: '2024-10-10',
});
