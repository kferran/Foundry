<script setup lang="ts">
import type { CalendarEvent } from '../model/types'

defineProps<{ event: CalendarEvent }>()
</script>

<template>
  <div class="kv"><span class="mono muted">{{ event.start }}–{{ event.end }}</span><span>{{ event.title }}</span></div>
</template>

<style scoped>
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.mono { font-family: var(--mono); }
.muted { color: var(--muted); }
</style>
