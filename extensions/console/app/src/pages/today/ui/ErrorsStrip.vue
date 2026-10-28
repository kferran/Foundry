<script setup lang="ts">
defineProps<{ fetchError: string; errors: string[] }>()
</script>

<template>
  <div v-if="fetchError || errors.length" class="errors" role="status">
    <p v-if="fetchError">Could not read the vault: {{ fetchError }}</p>
    <p v-for="e in errors" :key="e">{{ e }}</p>
  </div>
</template>

<style scoped>
.errors { margin: 16px 32px 0; padding: 10px 14px; border-radius: 8px; background: var(--warn-bg); color: var(--warn); font-size: 14px; }
.errors p { margin: 2px 0; }
@media (max-width: 640px) { .errors { margin-left: 16px; margin-right: 16px; } }
</style>
