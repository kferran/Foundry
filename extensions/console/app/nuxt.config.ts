// The console (console C1 spec §3): a single-page app; its Nitro server serves the page and two GET routes on
// 127.0.0.1 only. serve.sh sets NITRO_HOST and NITRO_PORT; server/plugins/host.ts refuses any other host.
export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  ssr: false,
  devtools: { enabled: false },
  telemetry: false,
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
