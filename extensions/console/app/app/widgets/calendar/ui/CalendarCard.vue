<script setup lang="ts">
import { type CalendarEvent, CalendarEventRow } from '@/entities/calendar-event'
import { Card } from '@/shared/ui'

defineProps<{ events: CalendarEvent[] }>()
</script>

<template>
  <Card heading="Calendar" heading-id="cal-h">
    <CalendarEventRow v-for="e in events" :key="e.start + e.title" :event="e" />
    <p v-if="!events.length" class="muted">Nothing in today's prep.</p>
  </Card>
</template>

<style scoped>
.muted { color: var(--muted); }
p { margin: 0; }
</style>
