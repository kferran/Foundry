// @vitest-environment happy-dom
// Each widget renders from its slice of the fixture, and its empty state (refactor plan Task 5).
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import fixture from '../fixtures/today.json'
import type { NowLine } from '@/entities/now-line'
import type { Project } from '@/entities/project'
import { CalendarCard } from '@/widgets/calendar'
import { ErrorsStrip } from '@/widgets/errors-strip'
import { FocusProjects } from '@/widgets/focus-projects'
import { HeaderBar } from '@/widgets/header-bar'
import { MeetingActions } from '@/widgets/meeting-actions'
import { NowLines } from '@/widgets/now-lines'
import { PipelineCard } from '@/widgets/pipeline'
import { SummaryTiles } from '@/widgets/summary-tiles'
import { TodayList } from '@/widgets/today-list'
import { WorkOrders } from '@/widgets/work-orders'

const work = fixture.partitions.work

describe('widgets', () => {
  it('HeaderBar shows the date, stamps and the Foreman link, and passes Refresh up', async () => {
    const w = mount(HeaderBar, { props: { date: '2026-10-24', foremanUrl: 'https://claude.ai/code', stamps: fixture.stamps, busy: false, partition: 'work' } })
    expect(w.text()).toContain('Read from prep 05:41 · index 09:12')
    expect(w.find('a.foreman').attributes('href')).toBe('https://claude.ai/code')
    await w.findAll('button').find((b) => b.text() === 'Refresh')!.trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
    expect(mount(HeaderBar, { props: { date: '', foremanUrl: '', stamps: null, busy: false, partition: 'work' } }).text())
      .toContain('Read from prep — · index —')
  })
  it('ErrorsStrip shows a fetch error and adapter errors, and nothing when there are none', () => {
    expect(mount(ErrorsStrip, { props: { fetchError: 'FetchError: 403', errors: ['calendar: no calendar.tsv'] } }).text())
      .toBe('Could not read the vault: FetchError: 403calendar: no calendar.tsv')
    expect(mount(ErrorsStrip, { props: { fetchError: '', errors: [] } }).find('.errors').exists()).toBe(false)
  })
  it('SummaryTiles shows the five counts', () => {
    const text = mount(SummaryTiles, { props: { tiles: work.tiles } }).text()
    for (const s of ['Focus2 of 51 stale', 'Needs you2', 'Overdue1', 'Waiting1', 'Work Orders1']) expect(text).toContain(s)
  })
  it('FocusProjects lists the cards and Also active, or says none are listed', () => {
    const text = mount(FocusProjects, { props: { projects: work.projects as Project[], alsoActive: work.also_active } }).text()
    expect(text).toContain('Focus projects 2 of 5')
    expect(text).toContain('Also active: Gamma')
    const empty = mount(FocusProjects, { props: { projects: [], alsoActive: [] } }).text()
    expect(empty).toContain('None listed in ActiveProjects.md.')
    expect(empty).not.toContain('Also active')
  })
  it('TodayList, CalendarCard and MeetingActions render their items and their empty states', () => {
    expect(mount(TodayList, { props: { items: work.today } }).text()).toContain('Write the runbook Alpha')
    expect(mount(TodayList, { props: { items: [] } }).text()).toContain('Nothing drawn.')
    expect(mount(CalendarCard, { props: { events: fixture.calendar } }).text()).toContain('Standup')
    expect(mount(CalendarCard, { props: { events: [] } }).text()).toContain("Nothing in today's prep.")
    expect(mount(MeetingActions, { props: { actions: work.actions } }).text()).toContain('Send the metrics')
    expect(mount(MeetingActions, { props: { actions: [] } }).text()).toContain('None.')
  })
  it('NowLines filters through its model and counts what it shows', async () => {
    const w = mount(NowLines, { props: { lines: work.now as NowLine[], unparsed: 1, filter: 'all', 'onUpdate:filter': (v: string) => w.setProps({ filter: v }) } })
    expect(w.findAll('tbody tr')).toHaveLength(3)
    expect(w.text()).toContain('1 hand-written line not shown')
    await w.findAll('button').find((b) => b.text() === 'Overdue')!.trigger('click')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.text()).toContain('1 of 3 open')
  })
  it('WorkOrders labels focus, shows held, and says when none ran', () => {
    const orders = [...fixture.orders.open, ...fixture.orders.today]
    const text = mount(WorkOrders, { props: { orders, projectLinks: ['Alpha', 'Beta'], held: 'usage 5h 70%' } }).text()
    expect(text).toMatch(/no PR yet · on focus/)
    expect(text).toMatch(/pull request · not on focus/)
    expect(text).toContain('Held: usage 5h 70%')
    expect(mount(WorkOrders, { props: { orders: [], projectLinks: [], held: null } }).text()).toContain('None queued or run today.')
  })
  it('PipelineCard shows the sources, quarantine and alerts', () => {
    const text = mount(PipelineCard, { props: fixture.pipeline }).text()
    expect(text).toContain('triage: failed: auth: expired')
    expect(text).toContain('Quarantine1')
    expect(text).toContain('Alerts today2')
  })
})
