import { assertLocalHost } from '../utils/auth'

// Refuse to start on anything but a loopback host (console C1 spec §6).
export default defineNitroPlugin(() => {
  assertLocalHost(process.env.NITRO_HOST || process.env.HOST)
})
