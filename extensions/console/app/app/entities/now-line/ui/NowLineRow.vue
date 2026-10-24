<script setup lang="ts">
import { isLink } from '@/shared/lib'
import { dueLabel } from '../lib/due'
import type { NowLine } from '../model/types'

defineProps<{ line: NowLine }>()
</script>

<template>
  <tr>
    <td class="mono">{{ line.kind }}</td>
    <td>{{ line.statement }}<div class="muted small">{{ line.who ? line.who + ', ' : '' }}since {{ line.since }}</div></td>
    <td class="small">{{ line.project || '—' }}</td>
    <td class="mono small" :class="{ warn: line.over }">{{ dueLabel(line) }}</td>
    <td class="small">
      <a v-if="isLink(line.evidence)" :href="line.evidence" target="_blank" rel="noopener">link</a><span v-else>{{ line.evidence }}</span>
    </td>
  </tr>
</template>

<style scoped>
td { padding: 8px; border-top: 1px solid var(--line-2); vertical-align: top; }
.mono { font-family: var(--mono); }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.warn { color: var(--warn); }
</style>
