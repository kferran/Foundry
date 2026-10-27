<script setup lang="ts">
defineProps<{ disabled?: boolean }>()
defineEmits<{ click: [] }>()
</script>

<template>
  <button type="button" class="btn" :disabled="disabled" @click="$emit('click')"><slot /></button>
</template>

<style scoped>
.btn { font: inherit; font-size: 13px; padding: 8px 14px; min-height: 36px; border: 1px solid var(--control); background: var(--card); border-radius: 6px; color: var(--ink); cursor: pointer; }
</style>
