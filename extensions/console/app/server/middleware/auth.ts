import { createError, defineEventHandler, getHeader } from 'h3'
import { refusal } from '../utils/auth'

export default defineEventHandler((event) => {
  const status = refusal(process.env, getHeader(event, 'tailscale-user-login'))
  if (status) {
    throw createError({ statusCode: status, statusMessage: status === 403 ? 'Forbidden' : 'Bad console_auth' })
  }
})
