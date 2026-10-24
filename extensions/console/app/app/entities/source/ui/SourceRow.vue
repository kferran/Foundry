<script setup lang="ts">
import { isHealthy } from '../lib/health'
import type { Source } from '../model/types'

defineProps<{ source: Source }>()
</script>

<template>
  <div class="kv"><span class="mono small" :class="{ warn: !isHealthy(source) }">{{ source }}</span></div>
</template>

<style scoped>
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.mono { font-family: var(--mono); }
.small { font-size: 13px; }
.warn { color: var(--warn); }
</style>
