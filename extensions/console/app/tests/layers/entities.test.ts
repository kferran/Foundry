// @vitest-environment happy-dom
// The small row entities: meeting-action, calendar-event and source, through their public APIs.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CalendarEventRow from '@/pages/today/ui/CalendarEventRow.vue'
import MeetingActionItem from '@/pages/today/ui/MeetingActionItem.vue'
import { isHealthy } from '@/pages/today/lib/health'
import SourceRow from '@/pages/today/ui/SourceRow.vue'

describe('row entities', () => {
  it('MeetingActionItem shows the action, its meeting and age', () => {
    const text = mount(MeetingActionItem, { props: { action: { bracket: 'Blake Sample', text: 'Send the metrics', meeting: '2026-10-21 Billing sync', age: '2 days open' } } }).text()
    expect(text).toContain('Send the metrics')
    expect(text).toContain('2026-10-21 Billing sync · 2 days open')
  })
  it('CalendarEventRow shows the span and title', () => {
    expect(mount(CalendarEventRow, { props: { event: { start: '09:30', end: '10:00', title: 'Standup' } } }).text()).toBe('09:30–10:00Standup')
  })
  it('a source is healthy when ok or off, and flagged otherwise', () => {
    expect(['calendar: ok', 'meetings: off', 'triage: failed: auth: expired', 'watch: unknown'].map(isHealthy))
      .toEqual([true, true, false, false])
    expect(mount(SourceRow, { props: { source: 'triage: failed: auth: expired' } }).find('.warn').exists()).toBe(true)
    expect(mount(SourceRow, { props: { source: 'calendar: ok' } }).find('.warn').exists()).toBe(false)
  })
})
