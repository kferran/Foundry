import { defineEventHandler, setResponseStatus } from 'h3'
import { runAdapter } from '../utils/run'

// Takes no query: the adapter's name and arguments are constants (ARCHITECTURE.md §3).
export default defineEventHandler(async (event) => {
  const result = await runAdapter(process.env.FOUNDRY_VAULT || '', 'today')
  setResponseStatus(event, result.status)
  return result.body
})
