<script setup lang="ts">
import { Chip } from '@/shared/ui'
import { FILTERS, type NowFilter } from '../model/useNowFilter'

const model = defineModel<NowFilter>({ required: true })
</script>

<template>
  <div role="group" aria-label="Filter Now lines" class="chips">
    <Chip v-for="[id, label] in FILTERS" :key="id" :pressed="model === id" @click="model = id">{{ label }}</Chip>
  </div>
</template>

<style scoped>
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
