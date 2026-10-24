import { slug } from '@/shared/lib'
import type { WorkOrder } from '../model/types'

/** On focus when the Work Order's id names a focus project (the #351 Task 3 rule, by slug). */
export function onFocus(order: Pick<WorkOrder, 'id'>, projectLinks: string[]): boolean {
  return projectLinks.map(slug).some((n) => n !== '' && order.id.includes(n))
}

/** The pull request a finished Work Order links, or "". */
export function prLink(order: Pick<WorkOrder, 'result'>): string {
  return order.result?.startsWith('https://') ? order.result : ''
}
