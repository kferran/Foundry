// Steiger checks the client's Feature-Sliced Design rules (ARCHITECTURE.md §2). Nothing is turned off: a rule it gets
// wrong is turned off here with a one-line reason, never dodged by moving code.
import fsd from '@feature-sliced/steiger-plugin'
import { defineConfig } from 'steiger'

export default defineConfig([...fsd.configs.recommended])
