import { expect, test } from 'claude-code/testing'
import { PROMPT, START, world } from './test-world'

const NOTE =
  'AgentZero plugin: the --said words were not found in what the operator typed in this session, so this was recorded as a proposal. Ask the operator.'
const REMEMBER = `./a0 memory remember "units are mm" --said "all in mm" --fact-key units --scope task --tag t --source-run r`
const PROPOSE = `./a0 memory propose fact 'units are mm' --fact-key units --scope task --tag t --source-run r`

test('words the operator typed: command unchanged', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('the project is all in mm, please remember'))
  const out = await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([REMEMBER])
  expect(out.context).toBeUndefined()
})

test('words the operator did not type: rewritten to propose fact with the note', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('the project is in millimetres'))
  const out = await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([PROPOSE])
  expect(out.context).toEqual([NOTE])
})

test('the rewrite keeps a leading cd', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.tool.call({ tool: 'Bash', command: 'cd /w && ./a0 memory remember "S" --said "nope"' })
  expect(w.commands).toEqual(['cd /w && ./a0 memory propose fact S'])
})

test('an unreadable remember: unchanged, one status message', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  const cmd = './a0 memory remember "S" --said "$X"'
  const out = await $.tool.call({ tool: 'Bash', command: cmd })
  expect(w.commands).toEqual([cmd])
  expect(out.context).toBeUndefined()
  expect(w.statuses).toEqual(["AgentZero: the operator's words in this remember were not checked"])
})

test('other commands pass untouched and silent', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.tool.call({ tool: 'Bash', command: 'ls -la' })
  await $.tool.call({ tool: 'Bash', command: './a0 memory review' })
  expect(w.commands).toEqual(['ls -la', './a0 memory review'])
  expect(w.statuses).toEqual([])
})

test('a prompt from a plugin or a task notification is not the operator\'s', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit({ text: 'all in mm', origin: { kind: 'task-notification' }, wait: false } as never)
  await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([PROPOSE])
})

test('a prompt from the bridge or the sdk is the operator\'s', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit({ text: 'all in mm', origin: { kind: 'bridge' }, wait: false })
  await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([REMEMBER])
})

test('after a resume, earlier user rows count', async ($, on) => {
  const w = world(on)
  w.messages = [
    { role: 'user', text: 'we work all in mm here', toolUses: [] },
    { role: 'assistant', text: 'ok', toolUses: [] },
  ]
  await $.session.start(START)
  await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([REMEMBER])
})

test('a user row that only carries a tool result does not count', async ($, on) => {
  const w = world(on)
  w.messages = [
    { role: 'user', text: 'all in mm', toolUses: [], toolResults: [{ tool_use_id: 't', text: 'all in mm', isError: false } as never] },
  ]
  await $.session.start(START)
  await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([PROPOSE])
})

test("a subagent's remember is checked against the main session's prompts", async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('everything is all in mm'))
  await $.tool.call({ tool: 'Bash', command: REMEMBER, agentId: 'sub1' } as never)
  expect(w.commands).toEqual([REMEMBER])
})

test('outside a workspace nothing is checked', async ($, on) => {
  const w = world(on, { existing: [] })
  await $.session.start(START)
  await $.tool.call({ tool: 'Bash', command: REMEMBER })
  await $.tool.call({ tool: 'Bash', command: './a0 memory remember "S" --said "$X"' })
  expect(w.commands).toEqual([REMEMBER, './a0 memory remember "S" --said "$X"'])
  expect(w.statuses).toEqual([])
})

test('words copied with other whitespace still match', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  await $.prompt.submit(PROMPT('it is\nall　in mm'))
  await $.tool.call({ tool: 'Bash', command: REMEMBER })
  expect(w.commands).toEqual([REMEMBER])
})
