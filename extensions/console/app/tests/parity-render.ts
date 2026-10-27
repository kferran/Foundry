// Renders the Today screen from the fixture for the parity check: TodayPage with the query answered from the fixture
// (before the refactor it mounted TodayView with the fixture as a prop). One line per heading, then the page text with
// whitespace dropped.
import { mountToday } from './mount-today'

export async function renderToday(): Promise<string> {
  const w = await mountToday()
  const headings = w.findAll('h2').map((h) => `# ${h.text()}`)
  return [...headings, w.text().replace(/\s+/g, '')].join('\n') + '\n'
}
