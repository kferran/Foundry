import { useQuery } from '@tanstack/vue-query'
import { getJson } from '@/shared/api'
import { POLL_MS } from '@/shared/config'
import type { Today } from '../model/types'

// The screen's one read (ARCHITECTURE.md §2.5): every 60 s while the tab is visible, and on Refresh.
export function useTodayQuery() {
  return useQuery({
    queryKey: ['today'],
    queryFn: () => getJson<Today>('/api/today'),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })
}
