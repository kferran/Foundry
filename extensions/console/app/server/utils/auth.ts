// Who gets an answer (console C1 spec §6). With CONSOLE_AUTH=tailscale only a request whose Tailscale-User-Login
// header equals CONSOLE_LOGIN does; an empty CONSOLE_LOGIN refuses everyone, so a fresh install answers nobody.
// tailscale serve sets the header from the tailnet identity; the server binds 127.0.0.1, so nothing else reaches it.

export interface AuthEnv {
  CONSOLE_AUTH?: string
  CONSOLE_LOGIN?: string
}

/** 0 when the request may go on, else the HTTP status to answer with. */
export function refusal(env: AuthEnv, login: string | undefined): number {
  const mode = env.CONSOLE_AUTH || 'tailscale'
  if (mode === 'none') return 0
  if (mode !== 'tailscale') return 500
  const want = (env.CONSOLE_LOGIN || '').trim()
  if (!want) return 403
  return login === want ? 0 : 403
}

const LOCAL = new Set(['127.0.0.1', 'localhost', '::1'])

/** Throws unless the server is set to listen on a loopback host only. */
export function assertLocalHost(host: string | undefined): void {
  if (!host || !LOCAL.has(host)) {
    throw new Error(`console: NITRO_HOST must be 127.0.0.1, localhost or ::1, not ${JSON.stringify(host ?? '')}`)
  }
}
