<script setup lang="ts">
const { data, error, isFetching, refetch } = useToday()
</script>

<template>
  <TodayView :data="data ?? null" :fetch-error="error ? String(error) : ''" :busy="isFetching" @refresh="refetch()" />
</template>

<style>
:root {
  --ground: #F4F3EF;
  --card: #FFFFFF;
  --ink: #1C1C1A;
  --ink-2: #3D3C38;
  --muted: #5C5B56;
  --line: #DEDCD5;
  --line-2: #EFEEE9;
  --accent: #1F4FB8;
  --accent-ink: #163A8A;
  --accent-bg: #E6ECF9;
  --warn: #8A3B00;
  --warn-bg: #FBE9D7;
  --ok: #2F6B3A;
}
body { margin: 0; background: var(--ground); color: var(--ink); font-family: 'IBM Plex Sans', system-ui, sans-serif; }
a { color: var(--accent); }
a:hover { color: var(--accent-ink); }
</style>
