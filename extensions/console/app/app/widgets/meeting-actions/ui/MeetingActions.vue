<script setup lang="ts">
import { type MeetingAction, MeetingActionItem } from '@/entities/meeting-action'
import { Card } from '@/shared/ui'

defineProps<{ actions: MeetingAction[] }>()
</script>

<template>
  <Card heading="Your meeting actions" heading-id="mtg-h">
    <MeetingActionItem v-for="a in actions" :key="a.text + a.meeting" :action="a" />
    <p v-if="!actions.length" class="muted">None.</p>
  </Card>
</template>

<style scoped>
.muted { color: var(--muted); }
p { margin: 0; }
</style>
