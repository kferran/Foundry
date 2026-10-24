// The console (console C1 spec §3, ARCHITECTURE.md §2.4): a single-page app; its Nitro server serves the page and the
// API on 127.0.0.1 only. serve.sh sets NITRO_HOST and NITRO_PORT; server/plugins/host.ts refuses any other host.
// The client is Feature-Sliced Design: Nuxt reads routes from app/routes/ (the FSD pages layer is app/pages/), and
// nothing is auto-imported, so every import goes through a slice's public API where Steiger can see it.
// `@` is app/, Nuxt 4's default.
export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  ssr: false,
  devtools: { enabled: false },
  telemetry: false,
  dir: { pages: 'routes' },
  components: false,
  imports: { autoImport: false },
  css: ['@/app/styles/tokens.css'],
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
