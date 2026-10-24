// Renders the Today screen from the fixture for the parity check. Before the refactor it mounts TodayView; Task 6
// points it at TodayPage with the query mocked. The output is one line per heading, then the page text, normalised.
import type { mount as Mount } from '@vue/test-utils'
import TodayView from '../app/components/TodayView.vue'
import fixture from './fixtures/today.json'

export async function renderToday(mount: typeof Mount): Promise<string> {
  const w = mount(TodayView, { props: { data: structuredClone(fixture) } })
  const headings = w.findAll('h2').map((h) => `# ${h.text()}`)
  // Whitespace dropped: splitting a component into files changes the spaces between elements, never the text.
  return [...headings, w.text().replace(/\s+/g, '')].join('\n') + '\n'
}
