import { describe, expect, it } from 'vitest'
import { adapterArgs, type Adapter, type Exec, runAdapter, TIMEOUT_MS } from './run'

describe('runAdapter (ARCHITECTURE.md §3)', () => {
  const calls: { file: string; args: string[]; cwd: string; timeout: number; maxBuffer: number }[] = []
  const ok: Exec = (file, args, opts, cb) => { calls.push({ file, args, ...opts }); cb(null, '{"v": 1, "errors": []}') }

  it('runs scripts/today.py --json from the vault with constant arguments and a timeout', async () => {
    expect(await runAdapter('/srv/vault', 'today', ok)).toEqual({ status: 200, body: { v: 1, errors: [] } })
    expect(calls.at(-1)).toEqual({ file: 'python3', args: adapterArgs('/srv/vault', 'today'), cwd: '/srv/vault',
                                   timeout: TIMEOUT_MS, maxBuffer: 8 * 1024 * 1024 })
    expect(adapterArgs('/srv/vault', 'today')).toEqual(['/srv/vault/extensions/console/scripts/today.py', '--json'])
  })
  it('refuses a name outside the list and runs nothing', async () => {
    const before = calls.length
    const r = await runAdapter('/srv/vault', '../../bin/sh' as Adapter, ok)
    expect(r.status).toBe(500)
    expect(calls.length).toBe(before)
  })
  it('gives 502 with one error on a timeout, an exit and bad output', async () => {
    const killed: Exec = (_f, _a, _o, cb) => cb(Object.assign(new Error('x'), { killed: true }), '')
    const exit: Exec = (_f, _a, _o, cb) => cb(Object.assign(new Error('x'), { code: 2 }), '')
    const junk: Exec = (_f, _a, _o, cb) => cb(null, 'not json')
    expect(await runAdapter('/v', 'today', killed)).toEqual({ status: 502, body: { errors: ['today.py: timed out'] } })
    expect(await runAdapter('/v', 'today', exit)).toEqual({ status: 502, body: { errors: ['today.py: exit 2'] } })
    expect(await runAdapter('/v', 'today', junk)).toEqual({ status: 502, body: { errors: ['today.py: output is not JSON'] } })
  })
  it('refuses to run without a vault', async () => {
    expect((await runAdapter('', 'today', ok)).status).toBe(500)
  })
})
