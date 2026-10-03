import { expect, test } from 'claude-code/testing'
import { parseRemember, proposeCommand, saidFound, splitWords } from './words'

const FULL =
  './a0 memory remember "S" --said "W" --fact-key k --scope task --tag a --tag b --source-run r'

test('splitWords handles single, double and escaped quotes', () => {
  expect(splitWords(`./a0 memory remember "a b" --said 'c "d"'`)).toEqual([
    './a0', 'memory', 'remember', 'a b', '--said', 'c "d"',
  ])
  expect(splitWords('x "a \\"b\\"" y\\ z')).toEqual(['x', 'a "b"', 'y z'])
})

test('splitWords refuses what it cannot read', () => {
  expect(splitWords('echo "a')).toBeNull()
  expect(splitWords('x $(y)')).toBeNull()
  expect(splitWords('x `y`')).toBeNull()
  expect(splitWords('x $Y')).toBeNull()
  expect(splitWords('x "$Y"')).toBeNull()
  expect(splitWords("x 'abc")).toBeNull()
})

test('parseRemember reads every flag', () => {
  expect(parseRemember(FULL)).toEqual({
    kind: 'remember',
    call: {
      cd: null, prefix: ['./a0', 'memory'], sentence: 'S', said: 'W',
      factKey: 'k', scope: 'task', tags: ['a', 'b'], sourceRun: 'r',
    },
  })
})

test('parseRemember keeps a leading cd', () => {
  const r = parseRemember('cd /w && ./a0 memory remember "S" --said "W"')
  expect(r.kind === 'remember' && r.call.cd).toBe('/w')
})

test('parseRemember accepts python -m memory', () => {
  const r = parseRemember('PYTHONPATH=src python3 -m memory remember "S" --said "W"')
  expect(r.kind === 'remember' && r.call.prefix).toEqual([
    'PYTHONPATH=src', 'python3', '-m', 'memory',
  ])
})

test('parseRemember says none for other commands', () => {
  expect(parseRemember('./a0 memory review')).toEqual({ kind: 'none' })
  expect(parseRemember('ls')).toEqual({ kind: 'none' })
  expect(parseRemember('git commit -m "memory remember"')).toEqual({ kind: 'none' })
})

test('parseRemember says unreadable for other shapes', () => {
  expect(parseRemember('./a0 memory remember "S" --said "$X"')).toEqual({ kind: 'unreadable' })
  expect(
    parseRemember('a && ./a0 memory remember "S" --said "W" && b'),
  ).toEqual({ kind: 'unreadable' })
  expect(parseRemember('./a0 memory remember "S" --said "W" | tee x')).toEqual({ kind: 'unreadable' })
  expect(parseRemember('./a0 memory remember "S" --said "W" --workspace /x')).toEqual({ kind: 'unreadable' })
  expect(parseRemember('sh -c "./a0 memory remember S --said W"')).toEqual({ kind: 'unreadable' })
  expect(parseRemember('./a0 memory remember "S" --said')).toEqual({ kind: 'unreadable' })
})

test('saidFound matches a whole substring', () => {
  expect(saidFound('毫米', ['这个项目全部用毫米'])).toBe(true)
  expect(saidFound('厘米', ['这个项目全部用毫米'])).toBe(false)
})

test('saidFound matches across newline, U+3000 and U+00A0', () => {
  expect(saidFound('a b c', ['x a\n b　 c y'])).toBe(true)
  expect(saidFound('a b c', ['x a b  c'])).toBe(true)
})

test('saidFound is false for an empty prompt list', () => {
  expect(saidFound('a', [])).toBe(false)
  expect(saidFound('   ', ['anything'])).toBe(false)
})

test('proposeCommand round-trips through splitWords', () => {
  const r = parseRemember(FULL)
  if (r.kind !== 'remember') throw new Error('not parsed')
  expect(splitWords(proposeCommand(r.call))).toEqual([
    './a0', 'memory', 'propose', 'fact', 'S',
    '--fact-key', 'k', '--scope', 'task', '--tag', 'a', '--tag', 'b', '--source-run', 'r',
  ])
  expect(proposeCommand(r.call)).not.toContain('--said')
})

test("proposeCommand quotes a sentence with ' and $", () => {
  const sentence = "it's $5"
  const cmd = proposeCommand({ cd: null, prefix: ['./a0', 'memory'], sentence, said: 'x', tags: [] })
  expect(splitWords(cmd)).toEqual(['./a0', 'memory', 'propose', 'fact', sentence])
})

test('proposeCommand keeps a cd and quotes it', () => {
  const cmd = proposeCommand({ cd: '/my dir', prefix: ['./a0', 'memory'], sentence: 'S', said: 'W', tags: [] })
  expect(cmd.startsWith("cd '/my dir' && ./a0 memory propose fact S")).toBe(true)
})
