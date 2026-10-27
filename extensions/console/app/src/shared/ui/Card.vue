<script setup lang="ts">
// A bordered block. With `heading`, it is a labelled section (aria-labelledby) with an h2.
defineProps<{ heading?: string; headingId?: string }>()
</script>

<template>
  <section v-if="heading" class="card" :aria-labelledby="headingId">
    <h2 :id="headingId" class="h"><slot name="heading">{{ heading }}</slot></h2>
    <slot />
  </section>
  <div v-else class="card"><slot /></div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }
.h { margin: 0 0 8px; font-size: 17px; font-weight: 600; }
</style>
