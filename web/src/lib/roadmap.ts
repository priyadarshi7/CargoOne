import raw from '../../../docs/02-roadmap.md?raw'

export type ItemState = 'done' | 'doing' | 'todo'
export interface RoadmapItem {
  state: ItemState
  text: string
}
export interface Phase {
  title: string
  items: RoadmapItem[]
}

const STATES: Record<string, ItemState> = { x: 'done', '~': 'doing', ' ': 'todo' }

/** Parses docs/02-roadmap.md so the Progress page always matches the documented to-do list. */
export function parseRoadmap(md: string = raw): Phase[] {
  const phases: Phase[] = []
  for (const line of md.split(/\r?\n/)) {
    const h = /^## (Phase .+)$/.exec(line)
    if (h) {
      phases.push({ title: h[1], items: [] })
      continue
    }
    const item = /^- \[([ x~])\] (.+)$/.exec(line)
    if (item && phases.length) {
      phases[phases.length - 1].items.push({
        state: STATES[item[1]],
        text: item[2].replace(/\*\*|`/g, '').replace(/^P[0-2] /, ''),
      })
    }
  }
  return phases.filter((p) => p.items.length > 0)
}

export function summarize(phases: Phase[]) {
  const all = phases.flatMap((p) => p.items)
  const done = all.filter((i) => i.state === 'done').length
  const doing = all.filter((i) => i.state === 'doing').length
  return { total: all.length, done, doing, pct: all.length ? Math.round((done / all.length) * 100) : 0 }
}
