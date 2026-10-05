import { expect, test } from 'claude-code/testing'
import { world } from './test-world'

const R = './a0 memory remember "Use pnpm, never npm" --said "Use pnpm in this project, never npm."'
const ROW = (over: Record<string, unknown> = {}) => ({
  tool_use_id: 'tu1', tool: 'Bash', input: { command: R }, isRunning: false, isErrored: false, isInterrupted: false,
  output: { stdout: 'remembered: a — Use pnpm, never npm\n', stderr: '' }, ...over,
})

function mountRow($: any, surface: 'desktop' | 'terminal', props: Record<string, unknown>) {
  return $.ui.mount({ plugin: 'agentzero', surface, component: 'ToolUse', props, requestId: String(props.tool_use_id ?? 'tu1') })
}

for (const surface of ['desktop', 'terminal'] as const) {
  test(`a remember row draws the green card on ${surface}`, async ($, on) => {
    world(on)
    const ui = await mountRow($, surface, ROW())
    if (surface === 'desktop') {
      const svg = await ui.find({ type: 'Svg' })
      expect(svg?.props.alt).toBe('已记住：Use pnpm, never npm')
      expect(String(svg?.props.source)).toContain('✓ 已核对')
    } else {
      expect(await ui.find({ text: /已记住/ })).toBeDefined()
      expect(await ui.find({ text: /已核对/ })).toBeDefined()
    }
  })
}

test('running, errored and plain rows keep the engine drawing', async ($, on) => {
  const w = world(on)
  await mountRow($, 'desktop', ROW({ isRunning: true, output: undefined }))
  await mountRow($, 'desktop', ROW({ tool_use_id: 'tu2', isErrored: true }))
  await mountRow($, 'desktop', ROW({ tool_use_id: 'tu3', input: { command: 'ls' }, output: { stdout: 'x', stderr: '' } }))
  expect(w.engineDrew).toEqual(['ToolUse', 'ToolUse', 'ToolUse'])
})

test('outside a workspace no card is drawn', async ($, on) => {
  const w = world(on, { existing: [] })
  await mountRow($, 'desktop', ROW())
  expect(w.engineDrew).toEqual(['ToolUse'])
})

test('a rewritten remember draws the amber card', async ($, on) => {
  const w = world(on)
  await $.tool.call({ tool: 'Bash', command: R })
  const id = w.toolUseIds.at(-1)
  expect(w.commands.at(-1)).toContain('propose fact')
  const ui = await mountRow($, 'desktop', ROW({ tool_use_id: id, output: { stdout: 'proposed: a — Use pnpm, never npm\n', stderr: '' } }))
  const source = String((await ui.find({ type: 'Svg' }))?.props.source)
  expect(source).toContain('待你确认')
  expect(source).toContain('引用不在你说过的话里，已改为提议')
})

test('the raw command opens and closes', async ($, on) => {
  world(on)
  const ui = await mountRow($, 'desktop', ROW())
  expect(await ui.find({ type: 'Code' })).toBeUndefined()
  await ui.press({ key: 'az-raw-tu1' })
  const code = await ui.find({ type: 'Code' })
  expect(String(code?.props.source)).toContain(R)
  expect(String(code?.props.source)).toContain('remembered: a')
  await ui.press({ key: 'az-raw-tu1' })
  expect(await ui.find({ type: 'Code' })).toBeUndefined()
})

test('a read of a builtin skill draws the skill card', async ($, on) => {
  world(on)
  const ui = await mountRow($, 'desktop', {
    tool_use_id: 'tu5', tool: 'Read', input: { file_path: '/w/skills/builtin/analyze.md' },
    isRunning: false, isErrored: false, isInterrupted: false, output: { type: 'text' },
  })
  expect((await ui.find({ type: 'Svg' }))?.props.alt).toBe('使用技能：analyze')
})

test('on the terminal a folded group with a write opens; others stay folded', async ($, on) => {
  const w = world(on)
  const group = (calls: unknown[], isExpanded = false) =>
    $.ui.render({ surface: 'terminal', component: 'ToolGroup', props: { calls, isActive: false, isExpanded } } as never)
  await group([ROW()])
  expect(w.groupExpanded.at(-1)).toBe(true)
  await group([ROW({ input: { command: 'ls' }, output: { stdout: 'x', stderr: '' } })])
  expect(w.groupExpanded.at(-1)).toBe(false)
  await group([ROW({ isRunning: true })])
  expect(w.groupExpanded.at(-1)).toBe(false)
})

test('on the desktop a folded group with a write shows its cards itself', async ($, on) => {
  const w = world(on)
  const group = (calls: unknown[]) =>
    $.ui.render({ surface: 'desktop', component: 'ToolGroup', props: { calls, isActive: false, isExpanded: false } } as never)
  const drawn = JSON.stringify(await group([ROW(), ROW({ tool_use_id: 'tu2', input: { command: 'ls' }, output: { stdout: 'x', stderr: '' } })]))
  expect(drawn).toContain('已记住：Use pnpm, never npm')
  expect(drawn).toContain('另有 1 条命令')
  expect(w.engineDrew).toEqual([])
  await group([ROW({ input: { command: 'ls' }, output: { stdout: 'x', stderr: '' } })])
  expect(w.engineDrew).toEqual(['ToolGroup'])
})
