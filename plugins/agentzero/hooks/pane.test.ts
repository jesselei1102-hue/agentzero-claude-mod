import { expect, test } from 'claude-code/testing'
import { KIND_LABEL, REVIEW_PANE, REVIEW_TITLE, paneResult, paneRows, reviewArgv } from './pane'

const item = (id: string) => ({ id, kind: 'fact', sentence: id, provenance: 'agent proposed it', createdAt: null })

test('paneRows: open, decided and failed', () => {
  const a = item('fact:a'), b = item('fact:b'), c = item('fact:c'), d = item('fact:d')
  const out = paneRows([a, b, d], {
    'fact:a': { item: a, outcome: 'kept', message: '' },
    'fact:b': { item: b, outcome: 'failed', message: 'No pending item' },
    'fact:c': { item: c, outcome: 'rejected', message: '' },
  })
  expect(out.rows).toEqual([
    { item: a, state: 'kept', message: null },
    { item: b, state: 'failed', message: 'No pending item' },
    { item: d, state: 'open', message: null },
    { item: c, state: 'rejected', message: null },
  ])
  expect(out.open).toBe(2)
  expect(out.done).toBe(2)
})

test('paneResult and reviewArgv', () => {
  const a = item('fact:a')
  expect(paneResult(a, 'keep', { exitCode: 0, stdout: 'confirmed: fact:a — a', stderr: '' })).toEqual({ item: a, outcome: 'kept', message: '' })
  expect(paneResult(a, 'reject', { exitCode: 0, stdout: '', stderr: '' }).outcome).toBe('rejected')
  expect(paneResult(a, 'keep', { exitCode: 1, stdout: '', stderr: '\nNo pending item fact:a\nmore' })).toEqual({ item: a, outcome: 'failed', message: 'No pending item fact:a' })
  expect(paneResult(a, 'keep', { exitCode: 2, stdout: '', stderr: '' }).message).toBe('exit 2')
  expect(paneResult(a, 'keep', new Error('timed out after 10000 ms')).message).toBe('timed out')
  expect(paneResult(a, 'keep', new Error('spawn ENOENT')).message).toBe('could not run')
  expect(reviewArgv('/w', 'reject', 'fact:a')).toEqual(['/w/a0', 'memory', 'review', '--reject', 'fact:a'])
  expect(reviewArgv('/w', 'keep', 'fact:a')).toEqual(['/w/a0', 'memory', 'review', '--confirm', 'fact:a'])
  expect([KIND_LABEL.fact, KIND_LABEL.edge, KIND_LABEL.skill]).toEqual(['Fact', '关系', '技能'])
  expect([REVIEW_PANE, REVIEW_TITLE]).toEqual(['agentzero-review', 'AgentZero · 待确认'])
})
