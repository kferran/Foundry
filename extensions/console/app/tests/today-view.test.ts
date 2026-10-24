// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TodayView, { type Today } from '../app/components/TodayView.vue'
import fixture from './fixtures/today.json'

const data = () => structuredClone(fixture) as unknown as Today
const view = (d: Today | null = data(), extra = {}) => mount(TodayView, { props: { data: d, ...extra } })
const button = (w: ReturnType<typeof view>, label: string) => w.findAll('button').find((b) => b.text() === label)!

describe('TodayView (console C1 spec §4, plan Task 6)', () => {
  it('renders every mockup section from the fixture', () => {
    const text = view().text()
    for (const s of ['Focus projects', 'Today', 'Calendar', 'Your meeting actions', 'Now lines', 'Work Orders', 'Pipeline'])
      expect(text).toContain(s)
    expect(text).toContain('Read from prep 05:41 · index 09:12')
    expect(text).toContain('Write the runbook')
    expect(text).toContain('and 2 more on the page')
    expect(text).toContain('Standup')
    expect(text).toContain('Send the metrics')
    expect(text).toContain('Talk to the Foreman')
  })

  it('shows only the chosen partition', async () => {
    const w = view()
    expect(w.text()).toContain('Unrelated chore')
    expect(w.text()).not.toContain('garden club')
    await button(w, 'Personal').trigger('click')
    expect(w.text()).toContain('garden club')
    expect(w.text()).not.toContain('Unrelated chore')
    expect(w.text()).not.toContain('Send the metrics')
  })

  it('filters Now lines to the overdue ones', async () => {
    const w = view()
    await button(w, 'Overdue').trigger('click')
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('4 days over')
    expect(w.text()).toContain('1 of 3 open')
  })

  it('shows a stale flag and Also active only when present', () => {
    expect(view().text()).toContain('Stale: no change since 2026-10-16')
    expect(view().text()).toContain('Also active: Gamma')
    const d = data()
    for (const x of d.partitions.work.projects) x.stale = null
    d.partitions.work.also_active = []
    const text = view(d).text()
    expect(text).not.toContain('Stale:')
    expect(text).not.toContain('Also active')
  })

  it('shows errors in the strip and a failed fetch', () => {
    const d = data()
    d.errors = ['calendar: no calendar.tsv in today\'s prep']
    expect(view(d).find('.errors').text()).toContain('no calendar.tsv')
    expect(view(null, { fetchError: 'FetchError: 403' }).find('.errors').text()).toContain('403')
  })

  it('labels Work Orders on and off focus and links their pull requests', () => {
    const text = view().text()
    expect(text).toContain('2026-10-23-alpha-runbook')
    expect(text).toMatch(/no PR yet · on focus/)
    expect(text).toMatch(/pull request · not on focus/)
  })

  it('Refresh asks for a refetch', async () => {
    const w = view()
    await button(w, 'Refresh').trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
  })
})
