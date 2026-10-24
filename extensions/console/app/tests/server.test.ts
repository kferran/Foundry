import { describe, expect, it } from 'vitest'
import { assertLocalHost, refusal } from '../server/utils/auth'
import { type Exec, runToday, TIMEOUT_MS, todayArgs } from '../server/utils/run'

describe('refusal (console C1 spec §6)', () => {
  const env = { CONSOLE_AUTH: 'tailscale', CONSOLE_LOGIN: 'owner@example.com' }
  it('answers the matching login', () => expect(refusal(env, 'owner@example.com')).toBe(0))
  it('refuses no header and another login', () => {
    expect(refusal(env, undefined)).toBe(403)
    expect(refusal(env, 'other@example.com')).toBe(403)
  })
  it('refuses everyone while console_login is empty', () => {
    expect(refusal({ CONSOLE_AUTH: 'tailscale', CONSOLE_LOGIN: '' }, '')).toBe(403)
    expect(refusal({}, 'owner@example.com')).toBe(403)
  })
  it('passes everyone with console_auth none, and fails closed on an unknown mode', () => {
    expect(refusal({ CONSOLE_AUTH: 'none' }, undefined)).toBe(0)
    expect(refusal({ CONSOLE_AUTH: 'open', CONSOLE_LOGIN: 'owner@example.com' }, 'owner@example.com')).toBe(500)
  })
})

describe('assertLocalHost', () => {
  it('accepts loopback hosts only', () => {
    for (const h of ['127.0.0.1', 'localhost', '::1']) expect(() => assertLocalHost(h)).not.toThrow()
    for (const h of ['0.0.0.0', '', undefined, '192.168.1.5']) expect(() => assertLocalHost(h)).toThrow(/NITRO_HOST/)
  })
})

describe('runToday', () => {
  const calls: { file: string; args: string[]; cwd: string; timeout: number; maxBuffer: number }[] = []
  const ok: Exec = (file, args, opts, cb) => { calls.push({ file, args, ...opts }); cb(null, '{"v": 1, "errors": []}') }

  it('runs today.py --json from the vault with constant arguments and a timeout', async () => {
    const r = await runToday('/srv/vault', ok)
    expect(r).toEqual({ status: 200, body: { v: 1, errors: [] } })
    expect(calls.at(-1)).toEqual({ file: 'python3', args: todayArgs('/srv/vault'), cwd: '/srv/vault', timeout: TIMEOUT_MS,
                                   maxBuffer: 8 * 1024 * 1024 })
    expect(todayArgs('/srv/vault')).toEqual(['/srv/vault/extensions/console/scripts/today.py', '--json'])
  })
  it('gives 502 with one error on a timeout, an exit and bad output', async () => {
    const killed: Exec = (_f, _a, _o, cb) => cb(Object.assign(new Error('x'), { killed: true }), '')
    const exit: Exec = (_f, _a, _o, cb) => cb(Object.assign(new Error('x'), { code: 2 }), '')
    const junk: Exec = (_f, _a, _o, cb) => cb(null, 'not json')
    expect(await runToday('/v', killed)).toEqual({ status: 502, body: { errors: ['today.py: timed out'] } })
    expect(await runToday('/v', exit)).toEqual({ status: 502, body: { errors: ['today.py: exit 2'] } })
    expect(await runToday('/v', junk)).toEqual({ status: 502, body: { errors: ['today.py: output is not JSON'] } })
  })
  it('refuses to run without a vault', async () => {
    expect((await runToday('', ok)).status).toBe(500)
  })
})
