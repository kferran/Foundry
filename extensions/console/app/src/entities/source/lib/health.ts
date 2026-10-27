import type { Source } from '../model/types'

/** A source reading ok or off is healthy; failed, expired or unknown is not. */
export function isHealthy(source: Source): boolean {
  return /: (ok|off)$/.test(source)
}
