import { describe, expect, it } from 'vitest'
import { assertLocalHost, refusal } from './auth'

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
