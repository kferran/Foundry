import { ref } from 'vue'
import type { NowLine } from '@/entities/now-line'

export type NowFilter = 'all' | 'overdue' | 'owed' | 'waiting' | 'draft'
export const FILTERS: readonly (readonly [NowFilter, string])[] = [
  ['all', 'All'], ['overdue', 'Overdue'], ['owed', 'Owed'], ['waiting', 'Waiting'], ['draft', 'Drafts'],
]

export function useNowFilter() {
  return ref<NowFilter>('all')
}

/** The lines a filter shows: every line, the ones with an overdue band, or one kind. */
export function filterLines(lines: NowLine[], filter: NowFilter): NowLine[] {
  if (filter === 'all') return lines
  if (filter === 'overdue') return lines.filter((l) => !!l.band)
  return lines.filter((l) => l.kind === filter)
}
