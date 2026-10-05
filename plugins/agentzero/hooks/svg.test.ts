import { expect, test } from 'claude-code/testing'
import { bandModel } from './band'
import { PALETTE, bandSvg, cardSvg, escapeXml, paneHeaderSvg, pendingItemSvg, textWidth, wrap } from './svg'

test('escapeXml', () => {
  expect(escapeXml(`<a & "b" 'c'>`)).toBe('&lt;a &amp; &quot;b&quot; &apos;c&apos;&gt;')
})

test('textWidth counts CJK as full width', () => {
  expect(textWidth('中a', 12)).toBe(20)
})

test('wrap breaks at punctuation and cuts the last line', () => {
  expect(wrap('deploy-checklist：部署前先跑迁移、再看监控面板的检查清单', 18, 2)).toEqual(['deploy-checklist：', '部署前先跑迁移、再看监控面板的检查…'])
  expect(wrap('短句', 18, 2)).toEqual(['短句'])
  expect(wrap('abcdefghij klmnopqrstu', 12, 2)).toEqual(['abcdefghij', 'klmnopqrstu'])
})

test('bandSvg holds every pill and the ring', () => {
  const now = Date.parse('2026-10-05T10:00:00+08:00')
  const pending = [{ id: 'fact:a', kind: 'fact', sentence: 'a', provenance: 'p', createdAt: null }, { id: 'fact:b', kind: 'fact', sentence: 'b', provenance: 'p', createdAt: null }]
  const svg = bandSvg(bandModel({ snapshot: { active: 3, pending, hotSet: { at: '2026-10-05T09:57:00+08:00', factIds: [] } }, error: null, stale: false }, null, 41, now))
  for (const text of ['● AgentZero', '3 条生效', '2 条待确认', 'hot set · 3 分钟前', '上下文 41%']) expect(svg).toContain(text)
  expect(svg).toContain(PALETTE.amber.fg)
  expect(svg.startsWith('<svg')).toBe(true)
})

test('cardSvg escapes and cuts', () => {
  const svg = cardSvg({ icon: '📌', label: '已记住', tone: 'green', title: 'a<b & "c"' + 'x'.repeat(40), detail: 'd', outline: false })
  expect(svg).toContain('&lt;b')
  expect(svg).toContain('&amp;')
  expect(svg).not.toContain('a<b')
  expect(svg).toContain('…')
  expect(svg).toContain('已记住')
})

test('pendingItemSvg strikes a rejected item and shows a failure in red', () => {
  const item = { id: 'fact:a', kind: 'fact', sentence: 'Never deploy on Fridays', provenance: 'agent proposed it', createdAt: '2026-10-04T10:49:18+08:00' }
  const rejected = pendingItemSvg({ item, state: 'rejected', message: null })
  expect(rejected).toContain('line-through')
  expect(rejected).toContain('✗ 已拒绝')
  expect(rejected).toContain('10-04 10:49')
  const failed = pendingItemSvg({ item, state: 'failed', message: 'No pending item fact:a' })
  expect(failed).toContain(PALETTE.red.fg)
  expect(failed).toContain('No pending item fact:a')
  expect(paneHeaderSvg(1, 2)).toContain('2 条已处理')
})
