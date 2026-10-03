import { expect, test } from 'claude-code/testing'

test('session.start shows the loaded status', async ($, on) => {
  const seen: (string | undefined)[] = []
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('ui.status', async (_$, e) => {
    seen.push(e.text)
  })

  await $.session.start({ cwd: '/tmp/x', surface: 'terminal', isInteractive: true })

  expect(seen.length).toBe(1)
  expect(seen[0]?.startsWith('AgentZero plugin loaded: ')).toBe(true)
})

test('prompt.submit shows the origin kind as a toast', async ($, on) => {
  const toasts: string[] = []
  on('prompt.submit', async (_$, e) => ({ text: e.text }))
  on('ui.toast', async (_$, e) => {
    toasts.push(e.text)
  })

  await $.prompt.submit({ text: 'hi', origin: { kind: 'composer' }, wait: false })

  expect(toasts).toEqual(['origin: composer'])
})

test('tool.call for Bash reaches the engine bottom unchanged', async ($, on) => {
  let seen = ''
  on('tool.call', { tool: 'Bash' }, async (_$, e) => {
    seen = e.command
    return { result: { stdout: 'ok', stderr: '' } }
  })

  const out = await $.tool.call({ tool: 'Bash', command: 'echo hi' })

  expect(seen).toBe('echo hi')
  expect(out.deny).toBeUndefined()
})
