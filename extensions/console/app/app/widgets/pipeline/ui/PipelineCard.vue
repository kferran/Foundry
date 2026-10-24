<script setup lang="ts">
import { type Source, SourceRow } from '@/entities/source'
import { Card } from '@/shared/ui'

defineProps<{ sources: Source[]; quarantine: number; alerts: number }>()
</script>

<template>
  <Card heading="Pipeline" heading-id="pipe-h">
    <SourceRow v-for="s in sources" :key="s" :source="s" />
    <div class="kv"><span>Quarantine</span><span class="mono">{{ quarantine }}</span></div>
    <div class="kv"><span>Alerts today</span><span class="mono">{{ alerts }}</span></div>
  </Card>
</template>

<style scoped>
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.mono { font-family: var(--mono); }
</style>
