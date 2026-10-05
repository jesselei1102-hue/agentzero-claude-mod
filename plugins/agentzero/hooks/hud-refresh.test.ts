import { expect, test } from 'claude-code/testing'
import { PROMPT, START, world } from './test-world'

const R = './a0 memory remember "Use pnpm, never npm" --said "Use pnpm, never npm"'

test('session start loads the snapshot once', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  expect(w.snapshotRuns.length).toBe(1)
  expect(w.snapshotRuns[0].argv[0]).toBe('/usr/bin/python3')
  expect(String(w.snapshotRuns[0].argv[1]).endsWith('/tools/snapshot.py')).toBe(true)
  expect(w.snapshotRuns[0].argv[2]).toBe('/w')
  expect(w.snapshotRuns[0].init).toEqual({ cwd: '/w', env: { PYTHONPATH: '/w/src' }, timeoutMs: 2000 })
})

test('each prompt refreshes, with or without a hot set', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await $.prompt.submit(PROMPT('two'))
  expect(w.snapshotRuns.length).toBe(3)
})

test('a memory write refreshes, other commands do not', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('Use pnpm, never npm'))
  const before = w.snapshotRuns.length
  await $.tool.call({ tool: 'Bash', command: R })
  expect(w.snapshotRuns.length).toBe(before + 1)
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  await $.tool.call({ tool: 'Bash', command: './a0 memory review' })
  expect(w.snapshotRuns.length).toBe(before + 1)
})

test('outside a workspace the snapshot never runs', async ($, on) => {
  const w = world(on, { existing: [] })
  await $.session.start(START)
  await $.prompt.submit(PROMPT('one'))
  await $.tool.call({ tool: 'Bash', command: R })
  expect(w.snapshotRuns.length).toBe(0)
})

test('a denied write does not refresh', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  w.denyBash = true
  const before = w.snapshotRuns.length
  await $.tool.call({ tool: 'Bash', command: R })
  expect(w.snapshotRuns.length).toBe(before)
})
