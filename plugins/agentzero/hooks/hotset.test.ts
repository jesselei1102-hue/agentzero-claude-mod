import { expect, test } from 'claude-code/testing'
import { SIX_HOURS_MS, hintsFrom, hotSetContext, needsHotSet } from './hotset'

test('needsHotSet', () => {
  expect(needsHotSet({ lastAt: null, resetSince: false }, 0)).toBe(true)
  expect(needsHotSet({ lastAt: 0, resetSince: true }, 1)).toBe(true)
  expect(needsHotSet({ lastAt: 0, resetSince: false }, SIX_HOURS_MS)).toBe(false)
  expect(needsHotSet({ lastAt: 0, resetSince: false }, SIX_HOURS_MS + 1)).toBe(true)
})

test('hintsFrom cuts at 200 code points and flattens lines', () => {
  expect(Array.from(hintsFrom('中'.repeat(250))).length).toBe(200)
  expect(hintsFrom('a\nb\r\nc')).toBe('a b c')
  expect(Array.from(hintsFrom('😀'.repeat(250))).length).toBe(200)
})

test('hotSetContext puts the two exact lines first', () => {
  const lines = hotSetContext('## Facts (1)', '2026-10-04 10:00').split('\n')
  expect(lines[0]).toBe('AgentZero hot set, loaded by the Claude Code plugin at 2026-10-04 10:00.')
  expect(lines[1]).toBe(
    'Rule 3 is done for this session: do not run hot-set again unless your context is compacted or cleared.',
  )
  expect(lines[2]).toBe('')
  expect(lines.slice(3).join('\n')).toBe('## Facts (1)')
})
