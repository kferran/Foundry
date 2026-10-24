<script setup lang="ts">
import { Chip } from '@/shared/ui'
import { type Partition, PARTITIONS } from '../model/usePartition'

const model = defineModel<Partition>({ required: true })
</script>

<template>
  <nav aria-label="Partition" class="tabs">
    <Chip v-for="[id, label] in PARTITIONS" :key="id" shape="pill" :pressed="model === id" @click="model = id">{{ label }}</Chip>
  </nav>
</template>

<style scoped>
.tabs { display: flex; gap: 4px; background: var(--line-2); padding: 4px; border-radius: 8px; }
</style>
