<script setup lang="ts">
import { type Project } from '../model/types'
import ProjectCard from './ProjectCard.vue'

defineProps<{ projects: Project[]; alsoActive: string[] }>()
</script>

<template>
  <section aria-labelledby="focus-h" class="stack">
    <h2 id="focus-h">Focus projects <span class="muted">{{ projects.length }} of 5</span></h2>
    <p v-if="!projects.length" class="muted">None listed in ActiveProjects.md.</p>
    <ProjectCard v-for="p in projects" :key="p.link" :project="p" />
    <p v-if="alsoActive.length" class="also">Also active: {{ alsoActive.join(', ') }}</p>
  </section>
</template>

<style scoped>
.stack { display: flex; flex-direction: column; gap: 12px; }
h2 { margin: 0 0 8px; font-size: 17px; font-weight: 600; }
.muted { color: var(--muted); }
p { margin: 0; }
.also { font-size: 14px; color: var(--ink-2); }
</style>
