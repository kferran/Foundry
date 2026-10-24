// What a test sees for Nuxt's `#imports`: the only Nuxt helper the client imports is $fetch (shared/api), and a test
// that reaches it mocks it with vi.mock('#imports').
export const $fetch = (): Promise<never> => Promise.reject(new Error('$fetch is not available in tests; mock #imports'))
