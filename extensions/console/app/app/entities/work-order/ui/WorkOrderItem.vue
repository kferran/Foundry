<script setup lang="ts">
import { Tag } from '@/shared/ui'
import { prLink } from '../lib/focus'
import type { WorkOrder } from '../model/types'

defineProps<{ order: WorkOrder; onFocus: boolean }>()
</script>

<template>
  <div class="item">
    <div class="spread"><span class="mono small">{{ order.id }}</span><Tag tone="plain">{{ order.state }}</Tag></div>
    <div class="muted small">
      <a v-if="prLink(order)" :href="prLink(order)" target="_blank" rel="noopener">pull request</a><span v-else>{{ order.reason || 'no PR yet' }}</span>
      · {{ onFocus ? 'on focus' : 'not on focus' }}
    </div>
  </div>
</template>

<style scoped>
.item { padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.spread { display: flex; justify-content: space-between; gap: 8px; }
.mono { font-family: var(--mono); }
.muted { color: var(--muted); }
.small { font-size: 13px; }
</style>
