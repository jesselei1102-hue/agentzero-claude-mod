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
  if (Number.isNaN(at)) return '时间未知'
  const ago = now - at
  if (ago < MINUTE) return '刚刚'
  if (ago < HOUR) return `${Math.floor(ago / MINUTE)} 分钟前`
  if (ago < DAY) return `${Math.floor(ago / HOUR)} 小时前`
  return `${Math.floor(ago / DAY)} 天前`
}

export function bandModel(hud: HudState, hotSetError: string | null, contextPercent: number | undefined, now: number): BandModel {
  const snap = hud.snapshot
  const pills: Pill[] = [{ text: 'AgentZero', tone: 'ink' }]
  if (snap !== null) {
    pills.push({ text: `${snap.active} 条生效`, tone: 'green' })
    pills.push({ text: `${snap.pending.length} 条待确认`, tone: snap.pending.length > 0 ? 'amber' : 'grey' })
  } else {
    pills.push({ text: hud.error !== null ? '记忆状态读取失败' : '记忆读取中…', tone: 'grey' })
  }
  if (hotSetError !== null) pills.push({ text: `hot set 未加载（${hotSetError}）`, tone: 'red' })
  else if (snap?.hotSet?.at) pills.push({ text: `hot set · ${relativeTime(now, snap.hotSet.at)}`, tone: 'grey' })
  else pills.push({ text: 'hot set 尚未加载', tone: 'grey' })

  let ring: Ring | null = null
  if (contextPercent !== undefined) {
    const percent = Math.round(contextPercent)
    const warn = percent >= CONTEXT_WARN_PERCENT
    ring = { percent, tone: warn ? 'amber' : 'blue', note: warn ? '压缩后自动重新加载' : null }
  }
  return {
    pills,
    ring,
    showReview: snap !== null && snap.pending.length > 0,
    alt: snap !== null ? `AgentZero 记忆：${snap.active} 条生效，${snap.pending.length} 条待确认` : 'AgentZero 记忆：状态未知',
  }
}
