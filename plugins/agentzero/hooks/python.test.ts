import { expect, test } from 'claude-code/testing'
import { PYTHON_CANDIDATES, PYTHON_PROBE, findPython } from './python'

test('findPython takes the first passing candidate, probing with PYTHON_PROBE', async () => {
  const calls: string[][] = []
  const run = async (argv: string[]) => {
    calls.push(argv)
    return { exitCode: argv[0] === '/opt/homebrew/bin/python3' ? 0 : 1 }
  }
  expect(await findPython(run)).toBe('/opt/homebrew/bin/python3')
  expect(calls.map(c => c[0])).toEqual(['python3', 'python', '/usr/bin/python3', '/opt/homebrew/bin/python3'])
  for (const c of calls) expect(c.slice(1)).toEqual(['-c', PYTHON_PROBE])
})

test('findPython returns null when none passes', async () => {
  expect(await findPython(async () => ({ exitCode: 1 }))).toBeNull()
})

test('findPython treats a candidate that cannot start as failed', async () => {
  let n = 0
  const run = async () => {
    if (n++ === 0) throw new Error('ENOENT')
    return { exitCode: 0 }
  }
  expect(await findPython(run)).toBe('python')
})

test('the candidates are the launcher list, in order', () => {
  expect(PYTHON_CANDIDATES).toEqual([
    'python3', 'python', '/usr/bin/python3', '/opt/homebrew/bin/python3',
    '/usr/local/bin/python3', '/Library/Frameworks/Python.framework/Versions/Current/bin/python3',
  ])
})
