// The one command the server runs (console C1 spec §3): today.py --json, from the vault root, with an argument list
// (never a shell) and a timeout. Nothing from the request reaches it.
import { execFile } from 'node:child_process'
import { join } from 'node:path'

export const TIMEOUT_MS = 15000

export type Exec = (
  file: string,
  args: string[],
  opts: { cwd: string; timeout: number; maxBuffer: number },
  cb: (err: (Error & { killed?: boolean; code?: number | string }) | null, stdout: string) => void,
) => void

export interface Result {
  status: number
  body: unknown
}

export function todayArgs(vault: string): string[] {
  return [join(vault, 'extensions', 'console', 'scripts', 'today.py'), '--json']
}

export function runToday(vault: string, exec: Exec = execFile as unknown as Exec): Promise<Result> {
  return new Promise((resolve) => {
    if (!vault) {
      resolve({ status: 500, body: { errors: ['console: FOUNDRY_VAULT is not set'] } })
      return
    }
    exec('python3', todayArgs(vault), { cwd: vault, timeout: TIMEOUT_MS, maxBuffer: 8 * 1024 * 1024 }, (err, stdout) => {
      if (err) {
        const why = err.killed ? 'timed out' : `exit ${err.code ?? 'unknown'}`
        resolve({ status: 502, body: { errors: [`today.py: ${why}`] } })
        return
      }
      try {
        resolve({ status: 200, body: JSON.parse(stdout) })
      } catch {
        resolve({ status: 502, body: { errors: ['today.py: output is not JSON'] } })
      }
    })
  })
}
