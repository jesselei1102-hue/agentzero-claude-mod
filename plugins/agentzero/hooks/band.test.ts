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
  expect(relativeTime(NOW, '2026-10-05T09:59:30+08:00')).toBe('刚刚')
  expect(relativeTime(NOW, '2026-10-05T09:57:00+08:00')).toBe('3 分钟前')
  expect(relativeTime(NOW, '2026-10-05T07:00:00+08:00')).toBe('3 小时前')
  expect(relativeTime(NOW, '2026-10-03T10:00:00+08:00')).toBe('2 天前')
  expect(relativeTime(NOW, 'nope')).toBe('时间未知')
  expect(relativeTime(NOW, '2026-10-05T10:05:00+08:00')).toBe('刚刚')
})

test('band pills for a loaded snapshot', () => {
  const m = bandModel(hud(3, 2), null, 41, NOW)
  expect(m.pills.map(p => p.text)).toEqual(['AgentZero', '3 条生效', '2 条待确认', 'hot set · 3 分钟前'])
  expect(m.pills.map(p => p.tone)).toEqual(['ink', 'green', 'amber', 'grey'])
  expect(m.ring).toEqual({ percent: 41, tone: 'blue', note: null })
  expect(m.showReview).toBe(true)
  expect(m.alt).toBe('AgentZero 记忆：3 条生效，2 条待确认')
})

test('band states', () => {
  const none = bandModel(hud(3, 0), null, 41, NOW)
  expect(none.pills[2]).toEqual({ text: '0 条待确认', tone: 'grey' })
  expect(none.showReview).toBe(false)
  expect(bandModel(hud(3, 1), 'exit 1', 41, NOW).pills[3]).toEqual({ text: 'hot set 未加载（exit 1）', tone: 'red' })
  expect(bandModel(hud(3, 1, null), null, 41, NOW).pills[3]).toEqual({ text: 'hot set 尚未加载', tone: 'grey' })
  expect(bandModel(hud(3, 1), null, 85.4, NOW).ring).toEqual({ percent: 85, tone: 'amber', note: '压缩后自动重新加载' })
  expect(bandModel(hud(3, 1), null, undefined, NOW).ring).toBeNull()
  const failed = bandModel({ snapshot: null, error: 'timed out', stale: false }, null, 41, NOW)
  expect(failed.pills.map(p => p.text)).toEqual(['AgentZero', '记忆状态读取失败', 'hot set 尚未加载'])
  expect(failed.alt).toBe('AgentZero 记忆：状态未知')
  expect(failed.showReview).toBe(false)
  expect(bandModel({ snapshot: null, error: null, stale: false }, null, 41, NOW).pills[1]).toEqual({ text: '记忆读取中…', tone: 'grey' })
})
