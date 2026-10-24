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
