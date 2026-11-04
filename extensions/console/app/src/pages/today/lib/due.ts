import { plural } from '@/shared/lib'
import { type NowLine } from '../model/types'

/** "4 days over" past its date, else the due's month and day, else "". */
export function dueLabel(line: Pick<NowLine, 'over' | 'due'>): string {
  if (line.over) return `${plural(line.over, 'day')} over`
  return line.due ? line.due.slice(5) : ''
}
