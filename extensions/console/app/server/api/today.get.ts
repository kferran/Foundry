import { defineEventHandler, setResponseStatus } from 'h3'
import { runToday } from '../utils/run'

// Takes no query: the command's arguments are constants (console C1 spec §3).
export default defineEventHandler(async (event) => {
  const result = await runToday(process.env.FOUNDRY_VAULT || '')
  setResponseStatus(event, result.status)
  return result.body
})
