import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Tests import slices and server utils directly, without a Nuxt runtime (ARCHITECTURE.md §6). `@` is src/, as in
// Nuxt; `#imports` is Nuxt's, so a test mocks it. A component test picks happy-dom with its own
// `@vitest-environment` comment.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '#imports': fileURLToPath(new URL('./tests/imports-stub.ts', import.meta.url)),
    },
  },
  test: { include: ['src/**/*.test.ts', 'server/**/*.test.ts', 'tests/**/*.test.ts'], environment: 'node' },
})
