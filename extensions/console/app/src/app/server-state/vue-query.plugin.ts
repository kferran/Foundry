import { defineNuxtPlugin } from '#imports'
import { installVueQuery } from './vue-query'

// Registered in nuxt.config.ts `plugins`, so Nuxt runs it without a plugins/ folder outside the FSD layers.
export default defineNuxtPlugin((nuxtApp) => {
  installVueQuery(nuxtApp.vueApp)
})
