// Mounts the Today page as the app runs it: the real Vue Query client, $fetch answered from the fixture (or an error),
// and Vue's warn handler throwing, so a component or composable used without its import fails the test (the
// refactor's guard: nuxi build does not catch one).
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { TodayPage } from '@/pages/today'
import fixture from './fixtures/today.json'
import { setFetch } from './imports-stub'

export async function mountToday(answer: () => Promise<unknown> = () => Promise.resolve(structuredClone(fixture))) {
  setFetch(answer)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const w = mount(TodayPage, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      config: { warnHandler: (msg: string) => { throw new Error(`Vue warning: ${msg}`) } },
    },
  })
  await flushPromises()
  return w
}
