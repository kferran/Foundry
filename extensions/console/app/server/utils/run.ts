// The only commands the server runs (ARCHITECTURE.md §3, §4): one screen's adapter, scripts/<name>.py --json, from
// the vault root, with an argument list (never a shell) and a timeout. The name comes from a constant list, so nothing
// from a request reaches the command.
import { execFile } from 'node:child_process'
import { join } from 'node:path'

export const ADAPTERS = ['today'] as const
export type Adapter = (typeof ADAPTERS)[number]
export const TIMEOUT_MS = 15000
const MAX_BUFFER = 8 * 1024 * 1024

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

export function adapterArgs(vault: string, name: Adapter): string[] {
  return [join(vault, 'extensions', 'console', 'scripts', `${name}.py`), '--json']
}

export function runAdapter(vault: string, name: Adapter, exec: Exec = execFile as unknown as Exec): Promise<Result> {
  return new Promise((resolve) => {
    if (!(ADAPTERS as readonly string[]).includes(name)) {
      resolve({ status: 500, body: { errors: [`console: no adapter named ${JSON.stringify(name)}`] } })
      return
    }
    if (!vault) {
      resolve({ status: 500, body: { errors: ['console: FOUNDRY_VAULT is not set'] } })
      return
    }
    exec('python3', adapterArgs(vault, name), { cwd: vault, timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER }, (err, stdout) => {
      if (err) {
        const why = err.killed ? 'timed out' : `exit ${err.code ?? 'unknown'}`
        resolve({ status: 502, body: { errors: [`${name}.py: ${why}`] } })
        return
      }
      try {
        resolve({ status: 200, body: JSON.parse(stdout) })
      } catch {
        resolve({ status: 502, body: { errors: [`${name}.py: output is not JSON`] } })
      }
    })
  })
}
