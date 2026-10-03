import { expect, test } from 'claude-code/testing'
import { hotSetContext, SIX_HOURS_MS } from './hotset'
import { MSG, PROMPT, START, world } from './test-world'

const HOT = '## Facts (1)\n'

function lastContext(w: ReturnType<typeof world>) {
  return w.contexts[w.contexts.length - 1]
}

test('no workspace: nothing attached', async ($, on) => {
  const w = world(on, { existing: [] })
  await $.session.start(START)
  await $.prompt.submit(PROMPT('hello'))
  expect(lastContext(w)).toBeUndefined()
  expect(w.runs.length).toBe(0)
  expect(w.statuses).toEqual([])
})

test('first prompt attaches the hot set with hints', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('hello there'))
  const ctx = lastContext(w) ?? []
  expect(ctx.length).toBe(1)
  expect(ctx[0].endsWith('\n' + HOT.trimEnd())).toBe(true)
  expect(ctx[0].startsWith('AgentZero hot set, loaded by the Claude Code plugin at ')).toBe(true)
  expect(ctx[0].split('\n')[1]).toBe(hotSetContext('x', 't').split('\n')[1])
  expect(w.runs.length).toBe(1)
  expect(w.runs[0].argv).toEqual(['/w/a0', 'memory', 'hot-set', '--scope', 'project', '--hints', 'hello there'])
  expect(w.runs[0].init).toEqual({ cwd: '/w', timeoutMs: 10_000 })
})

test('second prompt attaches nothing', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await $.prompt.submit(PROMPT('two'))
  expect(lastContext(w)).toBeUndefined()
  expect(w.runs.length).toBe(1)
})

test('after session.compact the next prompt attaches again', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await $.session.compact({ trigger: 'manual', messages: [MSG] })
  await $.prompt.submit(PROMPT('two'))
  expect((lastContext(w) ?? []).length).toBe(1)
  expect(w.runs.length).toBe(2)
})

test('a speculative compaction does not reset', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await $.session.compact({ trigger: 'precompute', messages: [MSG] })
  await $.prompt.submit(PROMPT('two'))
  expect(w.runs.length).toBe(1)
})

test('after a /clear the next prompt attaches again', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await $.session.end({ reason: 'clear', sessionId: 's1', resume: { id: 's1' } })
  await $.prompt.submit(PROMPT('two'))
  expect((lastContext(w) ?? []).length).toBe(1)
  expect(w.runs.length).toBe(2)
})

test('after six hours on the mocked clock the next prompt attaches again', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await w.clock.advance(SIX_HOURS_MS)
  await $.prompt.submit(PROMPT('two'))
  expect(w.runs.length).toBe(1)
  await w.clock.advance(1)
  await $.prompt.submit(PROMPT('three'))
  expect(w.runs.length).toBe(2)
})

test('a0 fails: nothing attached and the status says why', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  w.setRun({ exitCode: 1, stdout: '' })
  await $.prompt.submit(PROMPT('one'))
  expect(lastContext(w)).toBeUndefined()
  expect(w.statuses).toEqual(['AgentZero: hot set not loaded (exit 1)'])
  expect(w.toasts).toEqual(['AgentZero: hot set not loaded (exit 1)'])
})

test('a0 times out: status says timed out', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  w.setRun(new Error('timed out after 10000 ms'))
  await $.prompt.submit(PROMPT('one'))
  expect(lastContext(w)).toBeUndefined()
  expect(w.statuses).toEqual(['AgentZero: hot set not loaded (timed out)'])
})

test('a0 prints nothing: status says no output', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  w.setRun({ exitCode: 0, stdout: '  \n' })
  await $.prompt.submit(PROMPT('one'))
  expect(lastContext(w)).toBeUndefined()
  expect(w.statuses).toEqual(['AgentZero: hot set not loaded (no output)'])
})

test('a0 missing: status says a0 not found, and nothing is run', async ($, on) => {
  const w = world(on)
  w.existing.delete('/w/a0')
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  expect(w.statuses).toEqual(['AgentZero: hot set not loaded (a0 not found)'])
  expect(w.runs.length).toBe(0)
})

test('a failed load is tried again on the next prompt', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  w.setRun({ exitCode: 1, stdout: '' })
  await $.prompt.submit(PROMPT('one'))
  w.setRun({ exitCode: 0, stdout: HOT })
  await $.prompt.submit(PROMPT('two'))
  expect((lastContext(w) ?? []).length).toBe(1)
})

test('hints with quotes and $ reach a0 as one argv item', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('say "x" $HOME'))
  expect(w.runs[0].argv[6]).toBe('say "x" $HOME')
  expect(w.runs[0].argv.length).toBe(7)
})

test('a prompt before session.start still finds the workspace', async ($, on) => {
  const w = world(on)
  await $.prompt.submit(PROMPT('one'))
  expect((lastContext(w) ?? []).length).toBe(1)
})
