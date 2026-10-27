// The Today screen's object, as today.py --json gives it (console C1 spec §4). The page owns it: it is built from the
// entities' types, and entities on one layer cannot import each other (ARCHITECTURE.md §2.1).
import type { CalendarEvent } from '@/entities/calendar-event'
import type { MeetingAction } from '@/entities/meeting-action'
import type { NowLine } from '@/entities/now-line'
import type { Project } from '@/entities/project'
import type { Source } from '@/entities/source'
import type { WorkOrder } from '@/entities/work-order'
import type { Tiles } from '@/widgets/summary-tiles'

export type Part = {
  tiles: Tiles
  projects: Project[]
  also_active: string[]
  today: { text: string; project: string }[]
  now: NowLine[]
  unparsed: number
  actions: MeetingAction[]
}

export type Today = {
  v: number
  date: string
  stamps: { prep: string; index: string }
  partitions: Record<'work' | 'personal', Part>
  calendar: CalendarEvent[]
  orders: { open: WorkOrder[]; today: WorkOrder[]; needs: { id: string; text: string }[]; held: string | null }
  pipeline: { sources: Source[]; quarantine: number; alerts: number }
  foreman_url: string
  errors: string[]
}
