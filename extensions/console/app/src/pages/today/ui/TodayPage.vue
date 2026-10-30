<script setup lang="ts">
// The Today screen (#377 Q1): the query and the page's UI state, and each widget given one part of the object. Only
// this file reads `partitions`, and it hands every widget the chosen partition's part (ARCHITECTURE.md §2.5).
import { computed } from 'vue'
import { useNowFilter } from '../model/useNowFilter'
import { usePartition } from '../model/usePartition'
import CalendarCard from './CalendarCard.vue'
import ErrorsStrip from './ErrorsStrip.vue'
import FocusProjects from './FocusProjects.vue'
import HeaderBar from './HeaderBar.vue'
import MeetingActions from './MeetingActions.vue'
import NowLines from './NowLines.vue'
import PipelineCard from './PipelineCard.vue'
import SummaryTiles from './SummaryTiles.vue'
import TodayList from './TodayList.vue'
import WorkOrders from './WorkOrders.vue'
import { useTodayQuery } from '../api/useTodayQuery'

const { data, error, isFetching, refetch } = useTodayQuery()
const partition = usePartition()
const filter = useNowFilter()

const part = computed(() => data.value?.partitions?.[partition.value] ?? null)
const orders = computed(() => [...(data.value?.orders.open ?? []), ...(data.value?.orders.today ?? [])])
const links = computed(() => (part.value?.projects ?? []).map((p) => p.link))
const fetchError = computed(() => (error.value ? String(error.value) : ''))
</script>

<template>
  <div class="page">
    <HeaderBar v-model:partition="partition" :date="data?.date ?? ''" :foreman-url="data?.foreman_url ?? ''"
               :stamps="data?.stamps ?? null" :busy="isFetching" @refresh="refetch()" />
    <ErrorsStrip :fetch-error="fetchError" :errors="data?.errors ?? []" />

    <main v-if="data && part" class="main">
      <SummaryTiles :tiles="part.tiles" />
      <div class="row">
        <FocusProjects class="wide" :projects="part.projects" :also-active="part.also_active" />
        <aside class="narrow stack">
          <TodayList :items="part.today" />
          <CalendarCard :events="data.calendar" />
          <MeetingActions :actions="part.actions" />
        </aside>
      </div>
      <div class="row">
        <NowLines v-model:filter="filter" class="wide" :lines="part.now" :unparsed="part.unparsed" />
        <aside class="narrow stack">
          <WorkOrders :orders="orders" :project-links="links" :held="data.orders.held" />
          <PipelineCard v-bind="data.pipeline" />
        </aside>
      </div>
      <p class="muted small">Read-only: nothing on this page writes to the vault.</p>
    </main>
    <main v-else-if="!fetchError" class="main"><p class="muted">Loading…</p></main>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; }
.main { max-width: 1376px; margin: 0 auto; padding: 24px 32px 48px; display: flex; flex-direction: column; gap: 24px; }
.row { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
.wide { flex: 999 1 640px; min-width: 0; }
.narrow { flex: 1 1 380px; min-width: 0; }
.stack { display: flex; flex-direction: column; gap: 12px; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
p { margin: 0; }
@media (max-width: 640px) { .main { padding-left: 16px; padding-right: 16px; } }
</style>
