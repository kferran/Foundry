<script setup lang="ts">
import { computed } from 'vue'
import { type NowLine } from '../model/types'
import NowLineRow from './NowLineRow.vue'
import { filterLines, type NowFilter } from '../model/useNowFilter'
import FilterChips from './FilterChips.vue'
import { plural } from '@/shared/lib'
import { Card } from '@/shared/ui'

const props = defineProps<{ lines: NowLine[]; unparsed: number }>()
const filter = defineModel<NowFilter>('filter', { required: true })
const shown = computed(() => filterLines(props.lines, filter.value))
</script>

<template>
  <Card>
    <section aria-labelledby="now-h">
      <div class="head-row">
        <h2 id="now-h">Now lines <span class="muted">{{ shown.length }} of {{ lines.length }} open</span></h2>
        <FilterChips v-model="filter" />
      </div>
      <div class="scroll">
        <table>
          <thead><tr><th>Kind</th><th>Statement</th><th>Project</th><th>Due</th><th>Evidence</th></tr></thead>
          <tbody><NowLineRow v-for="l in shown" :key="l.kind + l.statement + l.since" :line="l" /></tbody>
        </table>
      </div>
      <p v-if="unparsed" class="muted small">{{ plural(unparsed, 'hand-written line') }} not shown; see the Now page.</p>
    </section>
  </Card>
</template>

<style scoped>
.head-row { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 12px; margin-bottom: 12px; }
h2 { margin: 0; font-size: 17px; font-weight: 600; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 640px; }
th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 500; padding: 6px 8px; }
p { margin: 8px 0 0; }
</style>
