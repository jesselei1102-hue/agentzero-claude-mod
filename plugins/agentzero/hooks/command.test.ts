import { expect, test } from 'claude-code/testing'
import { PYTHON_PROBE } from './python'
import { START, world } from './test-world'

const probeOk = (argv: readonly string[]) => argv[1] === '-c'

function run($: any, args: string) {
  return $.command.run({ command: 'agentzero', args }) as Promise<{ text?: string }>
}

test('session.start registers /agentzero', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  expect(w.registered).toEqual(['agentzero'])
})

test("init runs the kernel's init and says to start a new session", async ($, on) => {
  const w = world(on, { root: '/proj', existing: [] })
  w.responder = argv => (probeOk(argv) ? { exitCode: 0 } : { exitCode: 0, stdout: 'workspace created' })
  const out = await run($, 'init')
  expect(w.runs[0].argv).toEqual(['python3', '-c', PYTHON_PROBE])
  expect(w.runs[1].argv).toEqual(['python3', '-m', 'adapter', 'init', '/proj', '--harness', 'claude'])
  const pythonPath = (w.runs[1].init as { env: Record<string, string> }).env.PYTHONPATH
  expect(pythonPath.endsWith('/plugins/agentzero/kernel/src')).toBe(true)
  expect(out.text).toContain('workspace created')
  expect(out.text).toContain('Start a new session')
})

for (const [name, root, existing] of [
  ['home', '/home/u', []],
  ['root', '/', []],
  ['a folder inside a workspace', '/w/sub', ['/w/System.md', '/w/memory']],
  ['a workspace itself', '/w', ['/w/System.md', '/w/memory']],
] as const) {
  test(`init refuses ${name}, and writes nothing`, async ($, on) => {
    const w = world(on, { root, existing: [...existing] })
    const out = await run($, 'init')
    expect(w.runs.length).toBe(0)
    expect(out.text).toContain(root)
    expect(out.text).toContain('was not set up')
  })
}

test('init refuses a folder with Role.md: the kernel\'s refusal is shown', async ($, on) => {
  const w = world(on, { root: '/proj', existing: [] })
  w.responder = argv => (probeOk(argv) ? { exitCode: 0 } : { exitCode: 1, stderr: 'refusing: Role.md already exists' })
  const out = await run($, 'init')
  expect(out.text).toContain('refusing: Role.md already exists')
  expect(out.text).not.toContain('Start a new session')
})

test('no usable Python: the message names it and the pip line', async ($, on) => {
  const w = world(on, { root: '/proj', existing: [] })
  w.responder = () => ({ exitCode: 1 })
  const out = await run($, 'init')
  expect(out.text).toContain('python3 -m pip install pyyaml')
  expect(w.runs.every(r => (r.argv as string[])[1] === '-c')).toBe(true)
})

test("upgrade never passes --force, and shows the kernel's output as is", async ($, on) => {
  const w = world(on, { root: '/w' })
  w.responder = argv => (probeOk(argv) ? { exitCode: 0 } : { exitCode: 1, stdout: 'stopped: System.md was edited' })
  const out = await run($, 'upgrade')
  expect(w.runs[1].argv).toEqual(['python3', '-m', 'adapter', 'materialize', '/w', '--harness', 'claude'])
  expect((w.runs[1].argv as string[]).includes('--force')).toBe(false)
  expect(out.text).toBe('stopped: System.md was edited')
})

test('upgrade and status outside a workspace say so and run nothing', async ($, on) => {
  const w = world(on, { root: '/proj', existing: [] })
  for (const sub of ['upgrade', 'status']) {
    expect((await run($, sub)).text).toContain('not inside an AgentZero workspace')
  }
  expect(w.runs.length).toBe(0)
})

test('status shows preflight output and both versions', async ($, on) => {
  const w = world(on, {
    root: '/w',
    files: {
      '/.claude-plugin/plugin.json': '{"version":"1.2.3"}',
      '/kernel/SOURCE.json': '{"version":"0.4.5","commit":"c7fcd47abcdef"}',
    },
  })
  w.responder = argv => (probeOk(argv) ? { exitCode: 0 } : { exitCode: 0, stdout: 'preflight ok' })
  const out = await run($, 'status')
  expect(w.runs[1].argv).toEqual(['python3', '-m', 'adapter', 'preflight', '/w'])
  expect(out.text).toBe('preflight ok\nplugin 1.2.3, kernel 0.4.5 (c7fcd47)')
})

test('unknown args show usage', async ($, on) => {
  const w = world(on)
  for (const args of ['', 'frobnicate', 'init-now']) {
    expect((await run($, args)).text).toContain('Usage: /agentzero')
  }
  expect(w.runs.length).toBe(0)
})
