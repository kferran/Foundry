<script setup lang="ts">
import { Card } from '@/shared/ui'

defineProps<{ items: { text: string; project: string }[] }>()
</script>

<template>
  <Card heading="Today" heading-id="today-h">
    <p class="muted small">Drawn from the focus projects' Next items. Not written to Now.</p>
    <ol><li v-for="o in items" :key="o.text">{{ o.text }} <span class="muted small">{{ o.project }}</span></li></ol>
    <p v-if="!items.length" class="muted">Nothing drawn.</p>
  </Card>
</template>

<style scoped>
.muted { color: var(--muted); }
.small { font-size: 13px; }
p { margin: 0 0 8px; }
ol { margin: 4px 0 0; padding-left: 18px; font-size: 14px; line-height: 1.5; }
</style>
