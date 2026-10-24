<script setup lang="ts">
// The Today screen as drawn in the mockup (#377 Q1), from today.py's object (console C1 spec §4). It only reads: the
// one button refetches. Each partition's tab shows that partition's object and nothing from the other.
import { computed, ref } from 'vue'

type Line = {
  kind: string; section: string; statement: string; who: string; since: string; evidence: string
  rec: string; due: string; over: number | null; band: string | null; project: string
}
type Project = {
  rank: number; link: string; path: string; focus: string; next: string[]; decisions: string[]
  decisions_more: number; stale: string | null; now_lines: number; prs: number; changed: string
}
type Part = {
  tiles: Record<string, number>; projects: Project[]; also_active: string[]
  today: { text: string; project: string }[]; now: Line[]; unparsed: number
  actions: { bracket: string; text: string; meeting: string; age: string }[]
}
type Order = { id: string; state: string; result?: string | null; reason?: string | null; partition?: string }
export type Today = {
  v: number; date: string; stamps: { prep: string; index: string }; partitions: Record<string, Part>
  calendar: { start: string; end: string; title: string }[]
  orders: { open: Order[]; today: Order[]; needs: { id: string; text: string }[]; held: string | null }
  pipeline: { sources: string[]; quarantine: number; alerts: number }; foreman_url: string; errors: string[]
}

const props = defineProps<{ data: Today | null; fetchError?: string; busy?: boolean }>()
defineEmits<{ refresh: [] }>()

const part = ref<'work' | 'personal'>('work')
const filter = ref<'all' | 'overdue' | 'owed' | 'waiting' | 'draft'>('all')
const FILTERS = [['all', 'All'], ['overdue', 'Overdue'], ['owed', 'Owed'], ['waiting', 'Waiting'], ['draft', 'Drafts']] as const
const PARTS = [['work', 'Work'], ['personal', 'Personal']] as const

const p = computed<Part | null>(() => props.data?.partitions?.[part.value] ?? null)
const lines = computed(() => (p.value?.now ?? []).filter((l) =>
  filter.value === 'all' ? true : filter.value === 'overdue' ? !!l.band : l.kind === filter.value))
const openTotal = computed(() => p.value?.now.length ?? 0)
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const orders = computed(() => {
  const all = [...(props.data?.orders.open ?? []), ...(props.data?.orders.today ?? [])]
  const names = (p.value?.projects ?? []).map((x) => slug(x.link))
  return all.map((o) => ({ ...o, onFocus: names.some((n) => n && o.id.includes(n)), pr: o.result?.startsWith('https://') ? o.result : '' }))
})
const obsidian = (path: string) => `obsidian://open?file=${encodeURIComponent(path)}`
const due = (l: Line) => (l.over ? `${l.over} day${l.over === 1 ? '' : 's'} over` : l.due ? l.due.slice(5) : '')
const isLink = (s: string) => /^https?:\/\//.test(s)
</script>

<template>
  <div class="page">
    <header class="bar">
      <div class="brand"><span class="name">Foundry</span><span class="mono muted">{{ data?.date ?? '' }}</span></div>
      <nav aria-label="Partition" class="tabs">
        <button v-for="[id, label] in PARTS" :key="id" type="button" :aria-pressed="part === id" :class="{ on: part === id }"
                @click="part = id">{{ label }}</button>
      </nav>
      <a v-if="data" class="foreman" :href="data.foreman_url" target="_blank" rel="noopener">Talk to the Foreman</a>
      <div class="stamp">
        <span class="mono">Read from prep {{ data?.stamps.prep || '—' }} · index {{ data?.stamps.index || '—' }}</span>
        <button type="button" class="btn" :disabled="busy" @click="$emit('refresh')">{{ busy ? 'Refreshing' : 'Refresh' }}</button>
      </div>
    </header>

    <div v-if="fetchError || data?.errors.length" class="errors" role="status">
      <p v-if="fetchError">Could not read the vault: {{ fetchError }}</p>
      <p v-for="e in data?.errors ?? []" :key="e">{{ e }}</p>
    </div>

    <main v-if="data && p" class="main">
      <div class="tiles">
        <div class="tile"><div class="label">Focus</div><div class="value">{{ p.tiles.focus }} of 5</div><div class="sub">{{ p.tiles.stale }} stale</div></div>
        <div class="tile"><div class="label">Needs you</div><div class="value">{{ p.tiles.needs_you }}</div><div class="sub">owed and drafts</div></div>
        <div class="tile"><div class="label">Overdue</div><div class="value" :class="{ warn: p.tiles.overdue }">{{ p.tiles.overdue }}</div><div class="sub">past their date</div></div>
        <div class="tile"><div class="label">Waiting</div><div class="value">{{ p.tiles.waiting }}</div><div class="sub">on others</div></div>
        <div class="tile"><div class="label">Work Orders</div><div class="value accent">{{ p.tiles.orders }}</div><div class="sub">open</div></div>
      </div>

      <div class="row">
        <section aria-labelledby="focus-h" class="wide stack">
          <h2 id="focus-h">Focus projects <span class="muted">{{ p.projects.length }} of 5</span></h2>
          <p v-if="!p.projects.length" class="muted">None listed in ActiveProjects.md.</p>
          <article v-for="x in p.projects" :key="x.link" class="card project">
            <div class="head">
              <span class="mono muted">{{ x.rank }}</span>
              <a :href="obsidian(x.path)" class="title">{{ x.link }}</a>
              <span class="focus">{{ x.focus }}</span>
              <span v-if="x.stale" class="tag">Stale: no change since {{ x.stale }}</span>
            </div>
            <div class="cols">
              <div><div class="label">Next</div><ul><li v-for="n in x.next" :key="n">{{ n }}</li></ul><p v-if="!x.next.length" class="muted">None open.</p></div>
              <div>
                <div class="label">Decisions waiting</div>
                <ul><li v-for="d in x.decisions" :key="d">{{ d }}</li><li v-if="x.decisions_more">and {{ x.decisions_more }} more on the page</li></ul>
                <p v-if="!x.decisions.length" class="muted">None.</p>
              </div>
            </div>
            <div class="foot">
              <span>{{ x.now_lines }} Now line{{ x.now_lines === 1 ? '' : 's' }}</span>
              <span>{{ x.prs }} open PR{{ x.prs === 1 ? '' : 's' }}</span>
              <span v-if="x.changed">changed {{ x.changed }}</span>
            </div>
          </article>
          <p v-if="p.also_active.length" class="also">Also active: {{ p.also_active.join(', ') }}</p>
        </section>

        <aside class="narrow stack">
          <section aria-labelledby="today-h" class="card">
            <h2 id="today-h">Today</h2>
            <p class="muted small">Drawn from the focus projects' Next items. Not written to Now.</p>
            <ol><li v-for="o in p.today" :key="o.text">{{ o.text }} <span class="muted small">{{ o.project }}</span></li></ol>
            <p v-if="!p.today.length" class="muted">Nothing drawn.</p>
          </section>
          <section aria-labelledby="cal-h" class="card">
            <h2 id="cal-h">Calendar</h2>
            <div v-for="c in data.calendar" :key="c.start + c.title" class="kv"><span class="mono muted">{{ c.start }}–{{ c.end }}</span><span>{{ c.title }}</span></div>
            <p v-if="!data.calendar.length" class="muted">Nothing in today's prep.</p>
          </section>
          <section aria-labelledby="mtg-h" class="card">
            <h2 id="mtg-h">Your meeting actions</h2>
            <div v-for="a in p.actions" :key="a.text + a.meeting" class="item"><div>{{ a.text }}</div><div class="muted small">{{ a.meeting }} · {{ a.age }}</div></div>
            <p v-if="!p.actions.length" class="muted">None.</p>
          </section>
        </aside>
      </div>

      <div class="row">
        <section aria-labelledby="now-h" class="wide card">
          <div class="head-row">
            <h2 id="now-h">Now lines <span class="muted">{{ lines.length }} of {{ openTotal }} open</span></h2>
            <div role="group" aria-label="Filter Now lines" class="chips">
              <button v-for="[id, label] in FILTERS" :key="id" type="button" :aria-pressed="filter === id" :class="{ on: filter === id }"
                      @click="filter = id">{{ label }}</button>
            </div>
          </div>
          <div class="scroll">
            <table>
              <thead><tr><th>Kind</th><th>Statement</th><th>Project</th><th>Due</th><th>Evidence</th></tr></thead>
              <tbody>
                <tr v-for="l in lines" :key="l.kind + l.statement + l.since">
                  <td class="mono">{{ l.kind }}</td>
                  <td>{{ l.statement }}<div class="muted small">{{ l.who ? l.who + ', ' : '' }}since {{ l.since }}</div></td>
                  <td class="small">{{ l.project || '—' }}</td>
                  <td class="mono small" :class="{ warn: l.over }">{{ due(l) }}</td>
                  <td class="small"><a v-if="isLink(l.evidence)" :href="l.evidence" target="_blank" rel="noopener">link</a><span v-else>{{ l.evidence }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="p.unparsed" class="muted small">{{ p.unparsed }} hand-written line{{ p.unparsed === 1 ? '' : 's' }} not shown; see the Now page.</p>
        </section>

        <aside class="narrow stack">
          <section aria-labelledby="wo-h" class="card">
            <h2 id="wo-h">Work Orders</h2>
            <div v-for="o in orders" :key="o.id + o.state" class="item">
              <div class="spread"><span class="mono small">{{ o.id }}</span><span class="tag plain">{{ o.state }}</span></div>
              <div class="muted small">
                <a v-if="o.pr" :href="o.pr" target="_blank" rel="noopener">pull request</a><span v-else>{{ o.reason || 'no PR yet' }}</span>
                · {{ o.onFocus ? 'on focus' : 'not on focus' }}
              </div>
            </div>
            <p v-if="!orders.length" class="muted">None queued or run today.</p>
            <p v-if="data.orders.held" class="muted small">Held: {{ data.orders.held }}</p>
          </section>
          <section aria-labelledby="pipe-h" class="card">
            <h2 id="pipe-h">Pipeline</h2>
            <div v-for="s in data.pipeline.sources" :key="s" class="kv"><span class="mono small" :class="{ warn: !/: (ok|off)$/.test(s) }">{{ s }}</span></div>
            <div class="kv"><span>Quarantine</span><span class="mono">{{ data.pipeline.quarantine }}</span></div>
            <div class="kv"><span>Alerts today</span><span class="mono">{{ data.pipeline.alerts }}</span></div>
          </section>
        </aside>
      </div>

      <p class="muted small">Read-only: nothing on this page writes to the vault.</p>
    </main>
    <main v-else-if="!fetchError" class="main"><p class="muted">Loading…</p></main>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; }
.mono { font-family: 'IBM Plex Mono', monospace; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.warn { color: var(--warn); }
.accent { color: var(--accent); }
h2 { margin: 0 0 8px; font-size: 17px; font-weight: 600; }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 16px 24px; padding: 16px 32px; background: var(--card); border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: baseline; gap: 10px; }
.name { font-weight: 600; font-size: 18px; letter-spacing: 0.02em; }
.tabs { display: flex; gap: 4px; background: var(--line-2); padding: 4px; border-radius: 8px; }
.tabs button, .chips button { font: inherit; font-size: 13px; cursor: pointer; min-height: 32px; }
.tabs button { padding: 6px 14px; border-radius: 6px; border: 1px solid transparent; background: transparent; color: var(--ink-2); }
.tabs button.on { background: var(--ink); border-color: var(--ink); color: #fff; }
.foreman { font-size: 14px; }
.stamp { flex: 1 1 200px; display: flex; justify-content: flex-end; align-items: center; gap: 12px; font-size: 13px; color: var(--muted); }
.btn { font: inherit; font-size: 13px; padding: 8px 14px; min-height: 36px; border: 1px solid #C9C7BF; background: var(--card); border-radius: 6px; color: var(--ink); cursor: pointer; }
.errors { margin: 16px 32px 0; padding: 10px 14px; border-radius: 8px; background: var(--warn-bg); color: var(--warn); font-size: 14px; }
.errors p { margin: 2px 0; }
.main { max-width: 1376px; margin: 0 auto; padding: 24px 32px 48px; display: flex; flex-direction: column; gap: 24px; }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; }
.tile { flex: 1 1 180px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
.value { font-size: 28px; font-weight: 600; margin-top: 4px; }
.sub { font-size: 13px; color: var(--muted); margin-top: 2px; }
.row { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
.wide { flex: 999 1 640px; min-width: 0; }
.narrow { flex: 1 1 380px; min-width: 0; }
.stack { display: flex; flex-direction: column; gap: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }
.project { display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 12px; }
.title { font-weight: 600; font-size: 16px; text-decoration: none; }
.focus { font-size: 14px; color: var(--ink-2); }
.tag { font-size: 12px; font-weight: 500; color: var(--warn); background: var(--warn-bg); border-radius: 4px; padding: 2px 8px; }
.tag.plain { color: var(--ink-2); background: var(--line-2); }
.cols { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
ul, ol { margin: 4px 0 0; padding-left: 18px; font-size: 14px; line-height: 1.5; }
.foot { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--muted); border-top: 1px solid var(--line-2); padding-top: 8px; }
.also { margin: 0; font-size: 14px; color: var(--ink-2); }
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.item { padding: 6px 0; border-top: 1px solid var(--line-2); font-size: 14px; }
.spread { display: flex; justify-content: space-between; gap: 8px; }
.head-row { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 12px; margin-bottom: 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chips button { padding: 6px 12px; border-radius: 999px; border: 1px solid #C9C7BF; background: var(--card); color: var(--ink-2); }
.chips button.on { border-color: var(--accent); background: var(--accent-bg); color: var(--accent-ink); }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 640px; }
th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 500; padding: 6px 8px; }
td { padding: 8px; border-top: 1px solid var(--line-2); vertical-align: top; }
@media (max-width: 640px) {
  .bar, .main { padding-left: 16px; padding-right: 16px; }
  .errors { margin-left: 16px; margin-right: 16px; }
  .cols { grid-template-columns: minmax(0, 1fr); }
}
</style>
