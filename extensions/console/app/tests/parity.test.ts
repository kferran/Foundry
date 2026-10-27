// @vitest-environment happy-dom
// The FSD refactor's parity check (refactor plan Task 1 and Task 7): the Today screen rendered from the fixture keeps
// the same section headings and text. RECORD=1 writes the reference from the current page; without it, the test
// compares the page against that reference.
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { renderToday } from './parity-render'

// Vitest runs from the app folder; under happy-dom import.meta.url is not a file URL.
const REF = resolve(process.cwd(), 'tests/fixtures/today.render.txt')

it('the Today screen renders the same headings and text as before the refactor', async () => {
  const text = await renderToday()
  if (process.env.RECORD === '1' || !existsSync(REF)) {
    writeFileSync(REF, text)
    return
  }
  expect(text).toBe(readFileSync(REF, 'utf-8'))
})
