// @vitest-environment happy-dom
// The Today page (refactor plan Task 6): the assertions the single TodayView test held, now against the page with its
// real query, plus the partition-wall rule. mountToday makes any Vue warning (an unimported component) fail.
import { readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import fixture from '../../../../tests/fixtures/today.json'
import { mountToday } from '../../../../tests/mount-today'

const button = (w: Awaited<ReturnType<typeof mountToday>>, label: string) => w.findAll('button').find((b) => b.text() === label)!

describe('TodayPage', () => {
  it('renders every mockup section from the fixture', async () => {
    const text = (await mountToday()).text()
    for (const s of ['Focus projects', 'Today', 'Calendar', 'Your meeting actions', 'Now lines', 'Work Orders', 'Pipeline'])
      expect(text).toContain(s)
    for (const s of ['Read from prep 05:41 · index 09:12', 'Write the runbook', 'and 2 more on the page', 'Standup', 'Send the metrics', 'Talk to the Foreman'])
      expect(text).toContain(s)
  })

  it('shows only the chosen partition', async () => {
    const w = await mountToday()
    expect(w.text()).toContain('Unrelated chore')
    expect(w.text()).not.toContain('garden club')
    await button(w, 'Personal').trigger('click')
    expect(w.text()).toContain('garden club')
    expect(w.text()).not.toContain('Unrelated chore')
    expect(w.text()).not.toContain('Send the metrics')
  })

  it('filters Now lines to the overdue ones', async () => {
    const w = await mountToday()
    await button(w, 'Overdue').trigger('click')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.findAll('tbody tr')[0].text()).toContain('4 days over')
    expect(w.text()).toContain('1 of 3 open')
  })

  it('shows a stale flag and Also active only when present', async () => {
    const text = (await mountToday()).text()
    expect(text).toContain('Stale: no change since 2026-10-16')
    expect(text).toContain('Also active: Gamma')
    const d = structuredClone(fixture)
    for (const x of d.partitions.work.projects) x.stale = null
    d.partitions.work.also_active = []
    const bare = (await mountToday(() => Promise.resolve(d))).text()
    expect(bare).not.toContain('Stale:')
    expect(bare).not.toContain('Also active')
  })

  it('shows adapter errors in the strip, and a failed fetch', async () => {
    const d = structuredClone(fixture)
    d.errors = ["calendar: no calendar.tsv in today's prep"]
    expect((await mountToday(() => Promise.resolve(d))).find('.errors').text()).toContain('no calendar.tsv')
    expect((await mountToday(() => Promise.reject(new Error('FetchError: 403')))).find('.errors').text()).toContain('403')
  })

  it('labels Work Orders on and off focus', async () => {
    const text = (await mountToday()).text()
    expect(text).toContain('2026-10-23-alpha-runbook')
    expect(text).toMatch(/no PR yet · on focus/)
    expect(text).toMatch(/pull request · not on focus/)
  })

  it('Refresh asks the query again', async () => {
    let calls = 0
    const w = await mountToday(() => { calls += 1; return Promise.resolve(structuredClone(fixture)) })
    await button(w, 'Refresh').trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(calls).toBe(2)
  })

  it('only TodayPage reads the partitions map: every block it renders gets the part of one partition', () => {
    const ui = resolve(process.cwd(), 'src/pages/today/ui')
    const naming = readdirSync(ui).filter((n) => n.endsWith('.vue') && n !== 'TodayPage.vue')
      .filter((n) => readFileSync(join(ui, n), 'utf-8').includes('partitions'))
    expect(naming).toEqual([])
  })
})
