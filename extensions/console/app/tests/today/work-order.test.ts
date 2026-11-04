// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { onFocus, prLink } from '@/pages/today/lib/focus'
import WorkOrderItem from '@/pages/today/ui/WorkOrderItem.vue'

describe('work-order', () => {
  it('onFocus matches a focus project by slug', () => {
    expect(onFocus({ id: '2026-10-23-alpha-runbook' }, ['Alpha', 'Beta'])).toBe(true)
    expect(onFocus({ id: '2026-10-22-market-page' }, ['Alpha', 'Beta'])).toBe(false)
    expect(onFocus({ id: '2026-10-22-x' }, ['!!'])).toBe(false)
  })
  it('prLink takes a URL result only', () => {
    expect(prLink({ result: 'https://github.com/acme/shop/pull/9' })).toBe('https://github.com/acme/shop/pull/9')
    expect(prLink({ result: 'done, no PR' })).toBe('')
    expect(prLink({ result: null })).toBe('')
  })
  it('WorkOrderItem shows the PR or the reason, and the focus label', () => {
    expect(mount(WorkOrderItem, { props: { order: { id: 'a', state: 'done', result: 'https://github.com/acme/shop/pull/9' }, onFocus: false } }).text())
      .toMatch(/pull request · not on focus/)
    expect(mount(WorkOrderItem, { props: { order: { id: 'b', state: 'blocked', reason: 'tests failed' }, onFocus: true } }).text())
      .toMatch(/tests failed · on focus/)
    expect(mount(WorkOrderItem, { props: { order: { id: 'c', state: 'queued' }, onFocus: true } }).text()).toMatch(/no PR yet · on focus/)
  })
})
