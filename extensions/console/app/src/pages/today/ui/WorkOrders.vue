<script setup lang="ts">
import { onFocus } from '../lib/focus'
import { type WorkOrder } from '../model/types'
import WorkOrderItem from './WorkOrderItem.vue'
import { Card } from '@/shared/ui'

defineProps<{ orders: WorkOrder[]; projectLinks: string[]; held: string | null }>()
</script>

<template>
  <Card heading="Work Orders" heading-id="wo-h">
    <WorkOrderItem v-for="o in orders" :key="o.id + o.state" :order="o" :on-focus="onFocus(o, projectLinks)" />
    <p v-if="!orders.length" class="muted">None queued or run today.</p>
    <p v-if="held" class="muted small">Held: {{ held }}</p>
  </Card>
</template>

<style scoped>
.muted { color: var(--muted); }
.small { font-size: 13px; }
p { margin: 0; }
</style>
