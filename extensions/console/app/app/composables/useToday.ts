import { useQuery } from '@tanstack/vue-query'

// The Today screen's one read (console C1 spec §2, #377 Q6): every 60 s while the tab is visible, and on Refresh.
export const POLL_MS = 60000

export function useToday() {
  return useQuery({
    queryKey: ['today'],
    queryFn: () => $fetch('/api/today'),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })
}
