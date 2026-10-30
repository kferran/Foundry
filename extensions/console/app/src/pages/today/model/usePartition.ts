import { ref } from 'vue'

// Which partition the page shows (ARCHITECTURE.md §2.5): one at a time, work first.
export type Partition = 'work' | 'personal'
export const PARTITIONS: readonly (readonly [Partition, string])[] = [['work', 'Work'], ['personal', 'Personal']]

export function usePartition() {
  return ref<Partition>('work')
}
