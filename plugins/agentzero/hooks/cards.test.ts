import { expect, test } from 'claude-code/testing'
import { textWidth } from './svg'
import { a0Command, cardForBash, cardForCall, cardForRead, groupCard, isMemoryWrite } from './cards'

const R = './a0 memory remember "Use pnpm, never npm" --said "Use pnpm in this project, never npm."'

test('a checked remember is a green card with the words', () => {
  expect(cardForBash(R, 'remembered: use-pnpm-1 — Use pnpm, never npm\n→ tell the operator', undefined)).toEqual({
    icon: '📌', label: 'Remembered', tone: 'green', title: 'Use pnpm, never npm',
    detail: 'Your words: “Use pnpm in this project, never npm.” ✓ checked', outline: false,
  })
})

test('a rewritten remember says the quote was not found', () => {
  expect(cardForBash(R, 'proposed: x — Use pnpm, never npm\n', 'rewritten')).toEqual({
    icon: '⏳', label: 'Waiting for you', tone: 'amber', title: 'Use pnpm, never npm', detail: 'Not in your words, so saved as a proposal', outline: false,
  })
})

test("the kernel's own downgrade says the sentence says more", () => {
  expect(cardForBash(R, 'proposed: x — Use pnpm, never npm\n  it says more than', undefined)?.detail).toBe('Says more than your words, so saved as a proposal')
})

test('an unchecked remember has a grey outline', () => {
  const card = cardForBash('./a0 memory remember "S" --said "$X"', 'remembered: s — S\n', 'unchecked')
  expect(card?.detail).toBe('Quote not checked')
  expect(card?.outline).toBe(true)
  expect(card?.tone).toBe('green')
})

test('every other write has its card', () => {
  const rows: [string, string, Partial<ReturnType<typeof cardForBash>>][] = [
    ['./a0 memory propose fact "Never deploy on Fridays."', 'proposed: friday-1 — Never deploy on Fridays.\n',
      { icon: '⏳', label: 'Waiting for you', tone: 'amber', title: 'Never deploy on Fridays.', detail: 'Inferred by the assistant' }],
    ['./a0 memory forget --fact-key units', 'forgot: fact:units-1 — Sizes are in mm\n',
      { icon: '🗑', label: 'Forgotten', tone: 'grey', title: 'Sizes are in mm', detail: null }],
    ['./a0 memory review --confirm fact:friday-1', 'confirmed: fact:friday-1 — Never deploy on Fridays.\n',
      { icon: '✓', label: 'Confirmed', tone: 'green', title: 'Never deploy on Fridays.', detail: 'fact:friday-1' }],
    ['./a0 memory review --reject fact:friday-1', 'rejected: fact:friday-1 — Never deploy on Fridays.\n',
      { icon: '✗', label: 'Rejected', tone: 'grey', title: 'Never deploy on Fridays.', detail: 'fact:friday-1' }],
    ['./a0 memory link Acme owns repo', 'linked: edge:e1 — Acme owns repo\n',
      { icon: '🔗', label: 'Linked', tone: 'blue', title: 'Acme owns repo', detail: null }],
    ['./a0 skills draft --id deploy-checklist --description "x"', 'drafted: skill:deploy-checklist — Check before each deploy\n',
      { icon: '🧩', label: 'Skill draft', tone: 'amber', title: 'deploy-checklist', detail: 'Check before each deploy' }],
    ['./a0 knowledge add docs/spec.pdf --type docs --name "Spec"', 'declared: spec (docs) — Spec — docs/spec.pdf\n',
      { icon: '📚', label: 'Knowledge added', tone: 'blue', title: 'Spec', detail: 'docs' }],
    [R, 'already remembered: use-pnpm-1 — Use pnpm, never npm\n',
      { icon: '📌', label: 'Remembered', tone: 'green', title: 'Use pnpm, never npm', detail: 'Already on record' }],
    ['./a0 memory propose fact "S"', 'already on record (proposed): s-1 — S\n',
      { icon: '⏳', label: 'Waiting for you', tone: 'amber', title: 'S', detail: 'Already on record' }],
  ]
  for (const [command, stdout, want] of rows) {
    expect(cardForBash(command, stdout, undefined), command).toEqual({ outline: false, ...want })
  }
})

test('skill use is a blue card', () => {
  const skill = (title: string) => ({ icon: '🧭', label: 'Skill used', tone: 'blue', title, detail: null, outline: false })
  expect(cardForBash('./a0 skills run deploy-checklist', 'whatever the script prints', undefined)).toEqual(skill('deploy-checklist'))
  expect(cardForRead('/w/skills/builtin/analyze.md', '/w')).toEqual(skill('analyze'))
  expect(cardForRead('/w/skills/deploy/SKILL.md', '/w')).toEqual(skill('deploy'))
  expect(cardForRead('/w/skills/notes.md', '/w')).toEqual(skill('notes'))
})

test('look-alikes are not cards', () => {
  expect(cardForBash('echo "./a0 memory remember x --said y"', 'remembered: a — x', undefined)).toBeNull()
  expect(cardForBash('./a0 memory review', 'Nothing is waiting for you.', undefined)).toBeNull()
  expect(cardForBash(R, 'remember refused: needs words', undefined)).toBeNull()
  expect(cardForBash('./a0 memory hot-set --scope project', 'proposed: not really — x', undefined)).toBeNull()
  expect(cardForRead('/w/skills/_routing.md', '/w')).toBeNull()
  expect(cardForRead('/w/skills/builtin/_shared.md', '/w')).toBeNull()
  expect(cardForRead('/other/skills/builtin/analyze.md', '/w')).toBeNull()
  expect(cardForRead('/w/skills/builtin/sub/x.md', '/w')).toBeNull()
})

test('isMemoryWrite', () => {
  for (const yes of [
    R, './a0 memory propose fact "S"', './a0 memory forget --fact-key k', './a0 memory review --confirm fact:a',
    './a0 memory link a owns b', './a0 memory promote episode:e "S"', './a0 skills draft --id x', './a0 knowledge add f --type docs',
    'cd /w && ./a0 memory forget --fact-key k', 'PYTHONPATH=src python3 -m memory remember "S" --said "S"',
  ]) expect(isMemoryWrite(yes), yes).toBe(true)
  for (const no of ['./a0 memory review', './a0 memory hot-set --scope project', './a0 memory lint', './a0 skills run x', './a0 skills list', 'ls'])
    expect(isMemoryWrite(no), no).toBe(false)
  expect(a0Command('cd /w && ./a0 memory forget --fact-key k')).toEqual({ module: 'memory', sub: 'forget', args: ['--fact-key', 'k'] })
})

test('cardForCall skips running, errored and interrupted calls', () => {
  const call = { tool: 'Bash', input: { command: R }, output: { stdout: 'remembered: a — S\n', stderr: '' }, isRunning: false, isErrored: false, isInterrupted: false, tool_use_id: 't1' }
  const marks = new Map([['t1', 'unchecked' as const]])
  expect(cardForCall(call, '/w', marks)?.detail).toBe('Quote not checked')
  expect(cardForCall({ ...call, isRunning: true }, '/w', marks)).toBeNull()
  expect(cardForCall({ ...call, isErrored: true }, '/w', marks)).toBeNull()
  expect(cardForCall({ ...call, isInterrupted: true }, '/w', marks)).toBeNull()
  expect(cardForCall({ tool: 'Read', input: { file_path: '/w/skills/builtin/analyze.md' }, isRunning: false, isErrored: false, isInterrupted: false }, '/w', marks)?.title).toBe('analyze')
  expect(cardForCall({ tool: 'Edit', input: {}, isRunning: false, isErrored: false, isInterrupted: false }, '/w', marks)).toBeNull()
})

test('a long quote is cut inside the quotes, keeping ✓ checked', () => {
  const said = 'Use pnpm in this project for every install, every script, every CI job and every deploy, never npm.'
  const card = cardForBash(`./a0 memory remember "Use pnpm" --said "${said}"`, 'remembered: a — Use pnpm\n', undefined)
  expect(card?.detail?.endsWith('…” ✓ checked')).toBe(true)
  expect(textWidth(card?.detail ?? '', 12.5) <= 564).toBe(true)
})

test('a shell read of a skill file is a skill card', () => {
  const lab = 'ls skills/builtin/ && cat skills/builtin/analyze.md 2>/dev/null || cat skills/builtin/analyze/*.md; echo ----; cat skills/builtin/_routing.md'
  const call = (command: string) => ({ tool: 'Bash', input: { command }, output: { stdout: 'x', stderr: '' }, isRunning: false, isErrored: false, isInterrupted: false })
  const none = new Map()
  expect(cardForCall(call(lab), '/w', none)).toEqual({ icon: '🧭', label: 'Skill used', tone: 'blue', title: 'analyze', detail: null, outline: false })
  expect(cardForCall(call('cat /w/skills/deploy/SKILL.md'), '/w', none)?.title).toBe('deploy')
  expect(cardForCall(call('head -40 skills/builtin/report.md skills/builtin/research.md'), '/w', none)?.title).toBe('report, research')
  expect(cardForCall(call('cat /other/skills/builtin/analyze.md'), '/w', none)).toBeNull()
  expect(cardForCall(call('cat skills/builtin/_routing.md'), '/w', none)).toBeNull()
  expect(cardForCall(call('ls skills/builtin/analyze.md'), '/w', none)).toBeNull()
})

test('groupCard draws an AgentZero call from the start', () => {
  const base = { tool: 'Bash', input: { command: R }, isRunning: false, isErrored: false, isInterrupted: false }
  const none = new Map()
  expect(groupCard({ ...base, isRunning: true }, '/w', none)).toEqual({ icon: '⏳', label: 'Recording', tone: 'grey', title: 'Use pnpm, never npm', detail: null, outline: false })
  expect(groupCard({ ...base, input: { command: './a0 memory propose fact "S"' }, isRunning: true }, '/w', none)?.title).toBe('memory propose')
  expect(groupCard({ ...base, isErrored: true, output: 'Exit code 1' }, '/w', none)).toEqual({ icon: '✗', label: 'Not recorded', tone: 'grey', title: 'Use pnpm, never npm', detail: null, outline: false })
  expect(groupCard({ ...base, output: { stdout: 'remembered: a — Use pnpm, never npm\n', stderr: '' } }, '/w', none)?.label).toBe('Remembered')
  expect(groupCard({ ...base, input: { command: 'cat skills/builtin/analyze.md' }, isRunning: true }, '/w', none)?.label).toBe('Skill used')
  expect(groupCard({ ...base, input: { command: 'ls' }, isRunning: true }, '/w', none)).toBeNull()
  expect(groupCard({ ...base, input: { command: 'ls' }, output: { stdout: 'x', stderr: '' } }, '/w', none)).toBeNull()
})
