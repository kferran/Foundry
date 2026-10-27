<script setup lang="ts">
withDefaults(defineProps<{ label: string; value: string | number; sub: string; tone?: 'plain' | 'warn' | 'accent' }>(), { tone: 'plain' })
</script>

<template>
  <div class="tile">
    <div class="label">{{ label }}</div>
    <div class="value" :class="tone">{{ value }}</div>
    <div class="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.tile { flex: 1 1 180px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
.value { font-size: 28px; font-weight: 600; margin-top: 4px; }
.warn { color: var(--warn); }
.accent { color: var(--accent); }
.sub { font-size: 13px; color: var(--muted); margin-top: 2px; }
</style>
