<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'warn' | 'plain' }>(), { tone: 'warn' })
</script>

<template>
  <span class="tag" :class="tone"><slot /></span>
</template>

<style scoped>
.tag { font-size: 12px; font-weight: 500; border-radius: 4px; padding: 2px 8px; white-space: nowrap; }
.warn { color: var(--warn); background: var(--warn-bg); }
.plain { color: var(--ink-2); background: var(--line-2); }
</style>
