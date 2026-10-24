// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { NowLine } from '@/entities/now-line'
import { FilterChips, filterLines } from '@/features/filter-now-lines'
import { RefreshButton } from '@/features/refresh-today'
import { PartitionTabs } from '@/features/switch-partition'

const line = (kind: NowLine['kind'], band: string | null): NowLine => ({
  kind, section: '', statement: `${kind} ${band}`, who: '', since: '2026-10-01', evidence: '', rec: '', due: '',
  over: band ? 3 : null, band, notes: [], raw: '', project: '',
})
const lines = [line('owed', '1-7'), line('waiting', null), line('draft', null), line('owed', null)]

describe('features', () => {
  it('filterLines for each of the five filters', () => {
    expect(filterLines(lines, 'all')).toHaveLength(4)
    expect(filterLines(lines, 'overdue').map((l) => l.statement)).toEqual(['owed 1-7'])
    expect(filterLines(lines, 'owed')).toHaveLength(2)
    expect(filterLines(lines, 'waiting')).toHaveLength(1)
    expect(filterLines(lines, 'draft')).toHaveLength(1)
  })
  it('PartitionTabs presses the chosen tab and updates its model', async () => {
    const w = mount(PartitionTabs, { props: { modelValue: 'work', 'onUpdate:modelValue': (v: string) => w.setProps({ modelValue: v }) } })
    const [work, personal] = w.findAll('button')
    expect(work.attributes('aria-pressed')).toBe('true')
    await personal.trigger('click')
    expect(w.props('modelValue')).toBe('personal')
    expect(w.findAll('button')[1].attributes('aria-pressed')).toBe('true')
  })
  it('FilterChips updates its model', async () => {
    const w = mount(FilterChips, { props: { modelValue: 'all', 'onUpdate:modelValue': (v: string) => w.setProps({ modelValue: v }) } })
    await w.findAll('button').find((b) => b.text() === 'Overdue')!.trigger('click')
    expect(w.props('modelValue')).toBe('overdue')
  })
  it('RefreshButton says Refreshing while busy and emits once per click', async () => {
    expect(mount(RefreshButton, { props: { busy: true } }).text()).toBe('Refreshing')
    const w = mount(RefreshButton, { props: { busy: false } })
    expect(w.text()).toBe('Refresh')
    await w.find('button').trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
  })
})
