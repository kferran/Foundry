import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import type { App } from 'vue'

// Server state is Vue Query only (ARCHITECTURE.md §2.5). One retry, and a refetch when the tab regains focus.
export function installVueQuery(app: App): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } })
  app.use(VueQueryPlugin, { queryClient })
}
