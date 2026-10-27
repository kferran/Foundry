// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { dueLabel } from './lib/due'
import type { NowLine } from './model/types'
import NowLineRow from './ui/NowLineRow.vue'

const line: NowLine = {
  kind: 'owed', section: 'Needs you', statement: 'Reply on the cap', who: 'Blake Sample', since: '2026-10-01',
  evidence: 'https://github.com/acme/shop/pull/7', rec: '', due: '2026-10-20', over: 4, band: '1-7', notes: [], raw: '', project: 'Alpha',
}

describe('now-line', () => {
  it('dueLabel: days over, else the date, else nothing', () => {
    expect(dueLabel({ over: 4, due: '2026-10-20' })).toBe('4 days over')
    expect(dueLabel({ over: 1, due: '2026-10-20' })).toBe('1 day over')
    expect(dueLabel({ over: null, due: '2026-10-29' })).toBe('10-29')
    expect(dueLabel({ over: null, due: '' })).toBe('')
  })
  it('NowLineRow shows the line and links evidence that is a URL', () => {
    const w = mount(NowLineRow, { props: { line }, attachTo: document.createElement('tbody') })
    expect(w.text()).toContain('Reply on the cap')
    expect(w.text()).toContain('Blake Sample, since 2026-10-01')
    expect(w.find('a').attributes('href')).toBe('https://github.com/acme/shop/pull/7')
    const plain = mount(NowLineRow, { props: { line: { ...line, evidence: 'ABC-123', who: '', project: '' } }, attachTo: document.createElement('tbody') })
    expect(plain.find('a').exists()).toBe(false)
    expect(plain.text()).toContain('ABC-123')
    expect(plain.text()).toContain('—')
  })
})
