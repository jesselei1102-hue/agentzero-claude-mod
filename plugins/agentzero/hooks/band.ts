import type { HudState } from '../types'
import type { Tone } from './cards'

export type PillTone = Tone | 'ink' | 'red'
export type Pill = { text: string; tone: PillTone }
export type Ring = { percent: number; tone: 'blue' | 'amber'; note: string | null }
export type BandModel = { pills: Pill[]; ring: Ring | null; showReview: boolean; alt: string }

export const CONTEXT_WARN_PERCENT = 80

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export function relativeTime(now: number, iso: string): string {
  const at = Date.parse(iso)
  if (Number.isNaN(at)) return 'time unknown'
  const ago = now - at
  if (ago < MINUTE) return 'just now'
  if (ago < HOUR) return `${Math.floor(ago / MINUTE)} min ago`
  if (ago < DAY) return `${Math.floor(ago / HOUR)} h ago`
  return `${Math.floor(ago / DAY)} d ago`
}

export function bandModel(hud: HudState, hotSetError: string | null, contextPercent: number | undefined, now: number): BandModel {
  const snap = hud.snapshot
  const pills: Pill[] = [{ text: 'AgentZero', tone: 'ink' }]
  if (snap !== null) {
    pills.push({ text: `${snap.active} active`, tone: 'green' })
    pills.push({ text: `${snap.pending.length} waiting`, tone: snap.pending.length > 0 ? 'amber' : 'grey' })
  } else {
    pills.push({ text: hud.error !== null ? 'memory unreadable' : 'reading memory…', tone: 'grey' })
  }
  if (hotSetError !== null) pills.push({ text: `hot set not loaded (${hotSetError})`, tone: 'red' })
  else if (snap?.hotSet?.at) pills.push({ text: `hot set · ${relativeTime(now, snap.hotSet.at)}`, tone: 'grey' })
  else pills.push({ text: 'hot set not loaded yet', tone: 'grey' })

  let ring: Ring | null = null
  if (contextPercent !== undefined) {
    const percent = Math.round(contextPercent)
    const warn = percent >= CONTEXT_WARN_PERCENT
    ring = { percent, tone: warn ? 'amber' : 'blue', note: warn ? 'reloads after compaction' : null }
  }
  return {
    pills,
    ring,
    showReview: snap !== null && snap.pending.length > 0,
    alt: snap !== null ? `AgentZero memory: ${snap.active} active, ${snap.pending.length} waiting` : 'AgentZero memory: state unknown',
  }
}
