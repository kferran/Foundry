// A Work Order as nightshift.py list --json (queued) or report --json (run today) gives it.
export type WorkOrder = {
  id: string
  state: string
  kind?: string
  partition?: string | null
  result?: string | null
  reason?: string | null
}
