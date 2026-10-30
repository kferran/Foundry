// The console (console C1 spec §3, ARCHITECTURE.md §2.4): a single-page app; its Nitro server serves the page and the
// API on 127.0.0.1 only. serve.sh sets NITRO_HOST and NITRO_PORT; server/plugins/host.ts refuses any other host.
// The client is Feature-Sliced Design under src/ (the FSD guide's layout; a root named app/ would read as FSD's app
// layer): Nuxt reads routes from src/routes/ (the FSD pages layer is src/pages/), and
// nothing of ours is auto-imported, so every import goes through a slice's public API where Steiger can see it.
// `components.dirs: []` scans no folder of ours and keeps Nuxt's built-ins (<NuxtPage>). `@` is src/, Nuxt's
// srcDir.
export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  srcDir: 'src',
  ssr: false,
  devtools: { enabled: false },
  telemetry: false,
  dir: { pages: 'routes' },
  components: { dirs: [] },
  imports: { autoImport: false },
  css: ['@/app/styles/tokens.css'],
  plugins: ['@/app/server-state/vue-query.plugin.ts'],
  app: {
    head: {
      title: 'Foundry: Today',
      htmlAttrs: { lang: 'en' },
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap',
        },
      ],
    },
  },
  nitro: { preset: 'node-server' },
})
