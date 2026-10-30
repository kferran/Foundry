// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { type Project } from '@/pages/today/model/types'
import ProjectCard from '@/pages/today/ui/ProjectCard.vue'

const alpha: Project = {
  rank: 1, link: 'Alpha', path: 'wiki/work/concepts/Alpha.md', focus: 'cutover plan', next: ['Write the runbook'],
  decisions: ['Retry cap'], decisions_more: 2, stale: null, now_lines: 1, prs: 2, changed: '2026-10-23',
}

describe('ProjectCard', () => {
  it('shows the project, its next items, decisions with the rest counted, and its counts', () => {
    const text = mount(ProjectCard, { props: { project: alpha } }).text()
    for (const s of ['Alpha', 'cutover plan', 'Write the runbook', 'Retry cap', 'and 2 more on the page', '1 Now line', '2 open PRs', 'changed 2026-10-23'])
      expect(text).toContain(s)
    expect(text).not.toContain('Stale')
  })
  it('shows the stale flag and the empty states', () => {
    const w = mount(ProjectCard, { props: { project: { ...alpha, stale: '2026-10-16', next: [], decisions: [], decisions_more: 0, changed: '' } } })
    expect(w.text()).toContain('Stale: no change since 2026-10-16')
    expect(w.text()).toContain('None open.')
    expect(w.text()).toContain('None.')
    expect(w.text()).not.toContain('changed')
  })
  it('links the page in Obsidian', () => {
    expect(mount(ProjectCard, { props: { project: alpha } }).find('a').attributes('href'))
      .toBe('obsidian://open?file=wiki%2Fwork%2Fconcepts%2FAlpha.md')
  })
})
