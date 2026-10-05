import { expect, test } from 'claude-code/testing'
import { EMPTY_HUD, RefreshGate, nextHud, parseSnapshot, readSnapshot, statusAfter } from './snapshot'
import type { RunInit, SnapshotResult } from './snapshot'
import { PYTHON_PROBE } from './python'

const OK_JSON =
  '{"schema":1,"active":2,"pending":[{"id":"fact:a","kind":"fact","sentence":"S","provenance":"agent proposed it","createdAt":null}],"hotSet":null}'
const SNAP = {
  active: 2,
  pending: [{ id: 'fact:a', kind: 'fact', sentence: 'S', provenance: 'agent proposed it', createdAt: null }],
  hotSet: null,
}
const OK: SnapshotResult = { ok: true, snapshot: SNAP }

test('parseSnapshot accepts the schema and rejects the rest', () => {
  expect(parseSnapshot(OK_JSON)).toEqual({ ok: true, snapshot: SNAP })
  expect(parseSnapshot('{"schema":1,"error":"boom"}')).toEqual({ ok: false, error: 'boom' })
  expect(parseSnapshot('not json')).toEqual({ ok: false, error: 'unreadable snapshot' })
  expect(parseSnapshot('{"schema":2}')).toEqual({ ok: false, error: 'unknown snapshot schema' })
  expect(parseSnapshot('{"schema":1,"active":"x","pending":[],"hotSet":null}')).toEqual({ ok: false, error: 'unreadable snapshot' })
  expect(parseSnapshot('{"schema":1,"active":1,"pending":[{"id":3}],"hotSet":null}')).toEqual({ ok: false, error: 'unreadable snapshot' })
  expect(
    parseSnapshot('{"schema":1,"active":0,"pending":[],"hotSet":{"at":"2026-10-05T09:57:00+08:00","factIds":["f1"]}}'),
  ).toEqual({ ok: true, snapshot: { active: 0, pending: [], hotSet: { at: '2026-10-05T09:57:00+08:00', factIds: ['f1'] } } })
})

test('nextHud keeps the last good snapshot and marks it stale on failure', () => {
  expect(nextHud(EMPTY_HUD, OK)).toEqual({ snapshot: SNAP, error: null, stale: false })
  expect(nextHud(EMPTY_HUD, { ok: false, error: 'boom' })).toEqual({ snapshot: null, error: 'boom', stale: false })
  const loaded = { snapshot: SNAP, error: null, stale: false }
  expect(nextHud(loaded, { ok: false, error: 'boom' })).toEqual({ snapshot: SNAP, error: 'boom', stale: true })
  expect(nextHud({ snapshot: SNAP, error: 'boom', stale: true }, OK)).toEqual(loaded)
})

test('statusAfter sets, clears and leaves the status line', () => {
  expect(statusAfter(EMPTY_HUD, { ok: false, error: 'timed out' })).toBe('AgentZero: 记忆状态读取失败（timed out）')
  expect(statusAfter({ ...EMPTY_HUD, error: 'x' }, OK)).toBeUndefined()
  expect(statusAfter(EMPTY_HUD, OK)).toBeNull()
})

type Call = { argv: string[]; init: RunInit }

function fakeIo(opts: { python?: string | Error; answer?: (argv: string[]) => { exitCode: number; stdout?: string; stderr?: string } | Error }) {
  const calls: Call[] = []
  return {
    calls,
    io: {
      pluginRoot: '/plug',
      read: async (path: string) => {
        if (opts.python === undefined || opts.python instanceof Error) throw opts.python ?? new Error('ENOENT')
        if (!path.endsWith('/memory/traces/a0.python')) throw new Error('unexpected read ' + path)
        return opts.python
      },
      run: async (argv: string[], init: RunInit) => {
        calls.push({ argv, init })
        const a = opts.answer ? opts.answer(argv) : { exitCode: 0, stdout: OK_JSON }
        if (a instanceof Error) throw a
        return { exitCode: a.exitCode, stdout: a.stdout ?? '', stderr: a.stderr ?? '' }
      },
    },
  }
}

test('readSnapshot runs the script with the cached Python', async () => {
  const { io, calls } = fakeIo({ python: '/opt/py\n' })
  expect(await readSnapshot(io, '/w1')).toEqual(OK)
  expect(calls).toEqual([
    { argv: ['/opt/py', '/plug/tools/snapshot.py', '/w1'], init: { cwd: '/w1', env: { PYTHONPATH: '/w1/src' }, timeoutMs: 2000 } },
  ])
})

test('readSnapshot falls back to findPython when a0.python is missing', async () => {
  const { io, calls } = fakeIo({
    answer: argv => (argv[1] === '-c' ? { exitCode: argv[0] === 'python3' && argv[2] === PYTHON_PROBE ? 0 : 1 } : { exitCode: 0, stdout: OK_JSON }),
  })
  expect(await readSnapshot(io, '/w2')).toEqual(OK)
  const script = calls.filter(c => c.argv[1] === '/plug/tools/snapshot.py')
  expect(script.length).toBe(1)
  expect(script[0].argv[0]).toBe('python3')
})

test('readSnapshot reports exit, timeout and no Python', async () => {
  const timeout = fakeIo({ python: '/opt/py', answer: () => new Error('timed out after 2000 ms') })
  expect(await readSnapshot(timeout.io, '/w3')).toEqual({ ok: false, error: 'timed out' })
  const broken = fakeIo({ python: '/opt/py', answer: () => new Error('spawn ENOENT') })
  expect(await readSnapshot(broken.io, '/w4')).toEqual({ ok: false, error: 'could not run' })
  const exit = fakeIo({ python: '/opt/py', answer: () => ({ exitCode: 1, stderr: '\nTraceback (most recent call last):\nX' }) })
  expect(await readSnapshot(exit.io, '/w5')).toEqual({ ok: false, error: 'exit 1: Traceback (most recent call last):' })
  const none = fakeIo({ answer: () => ({ exitCode: 1 }) })
  expect(await readSnapshot(none.io, '/w6')).toEqual({ ok: false, error: 'no usable Python 3.11 with PyYAML' })
})

function deferred() {
  let release = () => {}
  const done = new Promise<void>(r => {
    release = r
  })
  return { done, release }
}

test('RefreshGate runs one job at a time and runs the latest waiting job once', async () => {
  const gate = new RefreshGate()
  const log: string[] = []
  const hold = deferred()
  const job = (name: string, wait?: Promise<void>) => async () => {
    log.push(`${name} start`)
    if (wait) await wait
    log.push(`${name} end`)
  }
  const a = gate.run(job('A', hold.done))
  const b = gate.run(job('B'))
  const c = gate.run(job('C'))
  let bSettled = false
  void b.then(() => {
    bSettled = true
  })
  await Promise.resolve()
  expect(log).toEqual(['A start'])
  hold.release()
  await a
  await c
  expect(bSettled).toBe(true)
  expect(log).toEqual(['A start', 'A end', 'C start', 'C end'])
})

test('RefreshGate keeps going after a job throws', async () => {
  const gate = new RefreshGate()
  const log: string[] = []
  await gate.run(async () => {
    throw new Error('boom')
  })
  await gate.run(async () => {
    log.push('ran')
  })
  expect(log).toEqual(['ran'])
})
