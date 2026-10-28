<script setup lang="ts">
import { Button } from '@/shared/ui'
import { type Partition } from '../model/usePartition'
import PartitionTabs from './PartitionTabs.vue'

defineProps<{ date: string; foremanUrl: string; stamps: { prep: string; index: string } | null; busy: boolean }>()
defineEmits<{ refresh: [] }>()
const partition = defineModel<Partition>('partition', { required: true })
</script>

<template>
  <header class="bar">
    <div class="brand"><span class="name">Foundry</span><span class="mono muted">{{ date }}</span></div>
    <PartitionTabs v-model="partition" />
    <a v-if="foremanUrl" class="foreman" :href="foremanUrl" target="_blank" rel="noopener">Talk to the Foreman</a>
    <div class="stamp">
      <span class="mono">Read from prep {{ stamps?.prep || '—' }} · index {{ stamps?.index || '—' }}</span>
      <Button :disabled="busy" @click="$emit('refresh')">{{ busy ? 'Refreshing' : 'Refresh' }}</Button>
    </div>
  </header>
</template>

<style scoped>
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 16px 24px; padding: 16px 32px; background: var(--card); border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: baseline; gap: 10px; }
.name { font-weight: 600; font-size: 18px; letter-spacing: 0.02em; }
.mono { font-family: var(--mono); }
.muted { color: var(--muted); }
.foreman { font-size: 14px; }
.stamp { flex: 1 1 200px; display: flex; justify-content: flex-end; align-items: center; gap: 12px; font-size: 13px; color: var(--muted); }
@media (max-width: 640px) { .bar { padding-left: 16px; padding-right: 16px; } }
</style>
