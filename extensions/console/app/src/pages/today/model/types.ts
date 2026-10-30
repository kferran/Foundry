// The Today screen's object, as today.py --json gives it (console C1 spec §4). The page owns it: it is built from the
// entities' types, and entities on one layer cannot import each other (ARCHITECTURE.md §2.1).

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

// A partition's counts as today.py gives them (console C1 spec §4).
export type Tiles = { focus: number; stale: number; needs_you: number; waiting: number; overdue: number; orders: number }

// A focus project as today.py gives it (console C1 spec §4).
export type Project = {
  rank: number
  link: string
  path: string
  focus: string
  next: string[]
  decisions: string[]
  decisions_more: number
  stale: string | null
  now_lines: number
  prs: number
  changed: string
}

// An open Now line as now.py list --json gives it, with the project today.py matched (console C1 spec §4, §8.4).
export type NowLine = {
  kind: 'owed' | 'waiting' | 'draft'
  section: string
  statement: string
  who: string
  since: string
  evidence: string
  rec: string
  due: string
  over: number | null
  band: string | null
  notes: { date: string; text: string }[]
  raw: string
  project: string
}

// A Work Order as nightshift.py list --json (queued) or report --json (run today) gives it.
export type WorkOrder = {
  id: string
  state: string
  kind?: string
  partition?: string | null
  result?: string | null
  reason?: string | null
}

// One of your open meeting actions, from the Yours section of today's actions.md.
export type MeetingAction = { bracket: string; text: string; meeting: string; age: string }

// One of today's events, from the morning's calendar.tsv.
export type CalendarEvent = { start: string; end: string; title: string }

// One sources.md line, without its "- ": "<source>: <state>[: <reason>]".
export type Source = string
