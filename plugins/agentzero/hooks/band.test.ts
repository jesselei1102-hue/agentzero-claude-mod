import { expect, test } from 'claude-code/testing'
import type { HudState } from '../types'
import { bandModel, relativeTime } from './band'

const NOW = Date.parse('2026-10-05T10:00:00+08:00')
const item = (id: string) => ({ id, kind: 'fact', sentence: id, provenance: 'agent proposed it', createdAt: null })
const hud = (active: number, pending: number, at: string | null = '2026-10-05T09:57:00+08:00'): HudState => ({
  snapshot: { active, pending: Array.from({ length: pending }, (_, i) => item(`fact:${i}`)), hotSet: at === null ? null : { at, factIds: [] } },
  error: null,
  stale: false,
})

test('relativeTime', () => {
  expect(relativeTime(NOW, '2026-10-05T09:59:30+08:00')).toBe('just now')
  expect(relativeTime(NOW, '2026-10-05T09:57:00+08:00')).toBe('3 min ago')
  expect(relativeTime(NOW, '2026-10-05T07:00:00+08:00')).toBe('3 h ago')
  expect(relativeTime(NOW, '2026-10-03T10:00:00+08:00')).toBe('2 d ago')
  expect(relativeTime(NOW, 'nope')).toBe('time unknown')
  expect(relativeTime(NOW, '2026-10-05T10:05:00+08:00')).toBe('just now')
})

test('band pills for a loaded snapshot', () => {
  const m = bandModel(hud(3, 2), null, 41, NOW)
  expect(m.pills.map(p => p.text)).toEqual(['AgentZero', '3 active', '2 waiting', 'hot set · 3 min ago'])
  expect(m.pills.map(p => p.tone)).toEqual(['ink', 'green', 'amber', 'grey'])
  expect(m.ring).toEqual({ percent: 41, tone: 'blue', note: null })
  expect(m.showReview).toBe(true)
  expect(m.alt).toBe('AgentZero memory: 3 active, 2 waiting')
})

test('band states', () => {
  const none = bandModel(hud(3, 0), null, 41, NOW)
  expect(none.pills[2]).toEqual({ text: '0 waiting', tone: 'grey' })
  expect(none.showReview).toBe(false)
  expect(bandModel(hud(3, 1), 'exit 1', 41, NOW).pills[3]).toEqual({ text: 'hot set not loaded (exit 1)', tone: 'red' })
  expect(bandModel(hud(3, 1, null), null, 41, NOW).pills[3]).toEqual({ text: 'hot set not loaded yet', tone: 'grey' })
  expect(bandModel(hud(3, 1), null, 85.4, NOW).ring).toEqual({ percent: 85, tone: 'amber', note: 'reloads after compaction' })
  expect(bandModel(hud(3, 1), null, undefined, NOW).ring).toBeNull()
  const failed = bandModel({ snapshot: null, error: 'timed out', stale: false }, null, 41, NOW)
  expect(failed.pills.map(p => p.text)).toEqual(['AgentZero', 'memory unreadable', 'hot set not loaded yet'])
  expect(failed.alt).toBe('AgentZero memory: state unknown')
  expect(failed.showReview).toBe(false)
  expect(bandModel({ snapshot: null, error: null, stale: false }, null, 41, NOW).pills[1]).toEqual({ text: 'reading memory…', tone: 'grey' })
})
