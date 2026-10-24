<script setup lang="ts">
import { obsidianLink, plural } from '@/shared/lib'
import { Card, Tag } from '@/shared/ui'
import type { Project } from '../model/types'

defineProps<{ project: Project }>()
</script>

<template>
  <Card>
    <article class="project">
      <div class="head">
        <span class="mono muted">{{ project.rank }}</span>
        <a :href="obsidianLink(project.path)" class="title">{{ project.link }}</a>
        <span class="focus">{{ project.focus }}</span>
        <Tag v-if="project.stale">Stale: no change since {{ project.stale }}</Tag>
      </div>
      <div class="cols">
        <div>
          <div class="label">Next</div>
          <ul><li v-for="n in project.next" :key="n">{{ n }}</li></ul>
          <p v-if="!project.next.length" class="muted">None open.</p>
        </div>
        <div>
          <div class="label">Decisions waiting</div>
          <ul>
            <li v-for="d in project.decisions" :key="d">{{ d }}</li>
            <li v-if="project.decisions_more">and {{ project.decisions_more }} more on the page</li>
          </ul>
          <p v-if="!project.decisions.length" class="muted">None.</p>
        </div>
      </div>
      <div class="foot">
        <span>{{ plural(project.now_lines, 'Now line') }}</span>
        <span>{{ plural(project.prs, 'open PR') }}</span>
        <span v-if="project.changed">changed {{ project.changed }}</span>
      </div>
    </article>
  </Card>
</template>

<style scoped>
.project { display: flex; flex-direction: column; gap: 10px; }
.head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 12px; }
.mono { font-family: var(--mono); }
.muted { color: var(--muted); }
.title { font-weight: 600; font-size: 16px; text-decoration: none; }
.focus { font-size: 14px; color: var(--ink-2); }
.cols { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
ul { margin: 4px 0 0; padding-left: 18px; font-size: 14px; line-height: 1.5; }
p { margin: 4px 0 0; font-size: 14px; }
.foot { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--muted); border-top: 1px solid var(--line-2); padding-top: 8px; }
@media (max-width: 640px) { .cols { grid-template-columns: minmax(0, 1fr); } }
</style>
