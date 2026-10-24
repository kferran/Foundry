import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Unit tests import server/utils and the components directly, without a Nuxt runtime; a component test picks
// happy-dom with its own `@vitest-environment` comment.
export default defineConfig({
  plugins: [vue()],
  test: { include: ['tests/**/*.test.ts'], environment: 'node' },
})
