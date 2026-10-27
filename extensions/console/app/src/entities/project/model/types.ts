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
