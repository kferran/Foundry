<script setup lang="ts">
import { Tile } from '@/shared/ui'
import type { Tiles } from '../model/types'

defineProps<{ tiles: Tiles }>()
</script>

<template>
  <div class="tiles">
    <Tile label="Focus" :value="`${tiles.focus} of 5`" :sub="`${tiles.stale} stale`" />
    <Tile label="Needs you" :value="tiles.needs_you" sub="owed and drafts" />
    <Tile label="Overdue" :value="tiles.overdue" sub="past their date" :tone="tiles.overdue ? 'warn' : 'plain'" />
    <Tile label="Waiting" :value="tiles.waiting" sub="on others" />
    <Tile label="Work Orders" :value="tiles.orders" sub="open" tone="accent" />
  </div>
</template>

<style scoped>
.tiles { display: flex; flex-wrap: wrap; gap: 12px; }
</style>
