<script setup lang="ts">
import { type MeetingAction } from '../model/types'

defineProps<{ action: MeetingAction }>()
</script>

<template>
  <div class="item">
    <div>{{ action.text }}</div>
    <div class="muted small">{{ action.meeting }} · {{ action.age }}</div>
  </div>
</template>

<style scoped>
.item { padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
</style>
