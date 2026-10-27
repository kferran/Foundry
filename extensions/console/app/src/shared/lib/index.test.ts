import { describe, expect, it } from 'vitest'
import { isLink, obsidianLink, plural, slug } from './index'

describe('shared/lib', () => {
  it('plural counts 0, 1 and 2', () => {
    expect([0, 1, 2].map((n) => plural(n, 'line'))).toEqual(['0 lines', '1 line', '2 lines'])
  })
  it('isLink takes http and https only', () => {
    expect(isLink('https://github.com/x')).toBe(true)
    expect(isLink('http://x')).toBe(true)
    expect(isLink('ABC-123')).toBe(false)
    expect(isLink('')).toBe(false)
  })
  it('obsidianLink encodes the path', () => {
    expect(obsidianLink('wiki/work/concepts/Billing sync.md')).toBe('obsidian://open?file=wiki%2Fwork%2Fconcepts%2FBilling%20sync.md')
  })
  it('slug lowers and joins with single dashes', () => {
    expect(slug('Factory F2: extension boundary!')).toBe('factory-f2-extension-boundary')
    expect(slug('  Alpha  ')).toBe('alpha')
  })
})
