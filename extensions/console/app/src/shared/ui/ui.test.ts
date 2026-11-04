// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { Button, Card, Chip, Tag, Tile } from './index'

describe('shared/ui', () => {
  it('Chip sets aria-pressed and emits click', async () => {
    const w = mount(Chip, { props: { pressed: true }, slots: { default: 'Work' } })
    expect(w.attributes('aria-pressed')).toBe('true')
    expect(w.classes()).toContain('on')
    await w.trigger('click')
    expect(w.emitted('click')).toHaveLength(1)
    expect(mount(Chip, { props: { pressed: false } }).attributes('aria-pressed')).toBe('false')
  })
  it('Tag takes a tone', () => {
    expect(mount(Tag, { slots: { default: 'x' } }).classes()).toContain('warn')
    expect(mount(Tag, { props: { tone: 'plain' } }).classes()).toContain('plain')
  })
  it('Card with a heading is a labelled section', () => {
    const w = mount(Card, { props: { heading: 'Today', headingId: 'today-h' }, slots: { default: '<p>x</p>' } })
    expect(w.element.tagName).toBe('SECTION')
    expect(w.attributes('aria-labelledby')).toBe('today-h')
    expect(w.find('h2').text()).toBe('Today')
    expect(mount(Card).element.tagName).toBe('DIV')
  })
  it('Button emits click unless disabled', async () => {
    const w = mount(Button, { slots: { default: 'Refresh' } })
    await w.trigger('click')
    expect(w.emitted('click')).toHaveLength(1)
    expect(mount(Button, { props: { disabled: true } }).attributes('disabled')).toBeDefined()
  })
  it('Tile shows its label, value and sub line', () => {
    expect(mount(Tile, { props: { label: 'Overdue', value: 3, sub: 'past their date', tone: 'warn' } }).text())
      .toBe('Overdue3past their date')
  })
})
