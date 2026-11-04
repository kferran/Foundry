<script setup lang="ts">
// A toggle in a group: `pill` for the partition tabs, `round` for the filters.
withDefaults(defineProps<{ pressed: boolean; shape?: 'round' | 'pill' }>(), { shape: 'round' })
defineEmits<{ click: [] }>()
</script>

<template>
  <button type="button" class="chip" :class="[shape, { on: pressed }]" :aria-pressed="pressed" @click="$emit('click')">
    <slot />
  </button>
</template>

<style scoped>
.chip { font: inherit; font-size: 13px; cursor: pointer; min-height: 32px; }
.round { padding: 6px 12px; border-radius: 999px; border: 1px solid var(--control); background: var(--card); color: var(--ink-2); }
.round.on { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-ink); }
.pill { padding: 6px 14px; border-radius: 6px; border: 1px solid transparent; background: transparent; color: var(--ink-2); }
.pill.on { background: var(--ink); border-color: var(--ink); color: #fff; }
</style>
