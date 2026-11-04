// What a test sees for Nuxt's `#imports` (vitest.config.ts). The client imports $fetch (shared/api) and the app layer
// defineNuxtPlugin; a test answers $fetch with setFetch().
type Fetch = (path: string) => Promise<unknown>
let current: Fetch = () => Promise.reject(new Error('$fetch is not set in this test; call setFetch()'))

export function setFetch(fn: Fetch): void {
  current = fn
}

export const $fetch = <T>(path: string): Promise<T> => current(path) as Promise<T>
export const defineNuxtPlugin = <T>(fn: T): T => fn
