import { expect, test } from 'claude-code/testing'
import { PROMPT, SNAPSHOT, START, world } from './test-world'

const BAND = { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120, scroll: { offset: 0, bodyRows: 10 }, view: {} }
const PANE = { title: 'AgentZero · 待确认', isFocused: false, bodyColumns: 60, placement: 'dock' as const, scroll: { offset: 0, bodyRows: 30 }, view: {} }
const EMPTY = JSON.stringify({ ...SNAPSHOT, pending: [] })

async function bandSource(ui: { find: (q: { type: string }) => Promise<{ props: Record<string, unknown> } | undefined> }) {
  return String((await ui.find({ type: 'Svg' }))?.props.source ?? '')
}

for (const surface of ['desktop', 'terminal'] as const) {
  test(`the band shows the snapshot on ${surface}`, async ($, on) => {
    world(on)
    await $.session.start(START)
    const ui = await $.ui.mount({ plugin: 'agentzero', surface, component: 'AbovePrompt', props: BAND })
    if (surface === 'desktop') {
      const svg = await ui.find({ type: 'Svg' })
      expect(svg?.props.alt).toBe('AgentZero 记忆：3 条生效，1 条待确认')
      expect(String(svg?.props.source)).toContain('上下文 41%')
    } else {
      expect(await ui.find({ text: '3 条生效' })).toBeDefined()
      expect(await ui.find({ text: '上下文 41%' })).toBeDefined()
    }
  })
}

test('the review button opens the pane and refreshes', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  const ui = await $.ui.mount({ plugin: 'agentzero', surface: 'desktop', component: 'AbovePrompt', props: BAND })
  const before = w.snapshotRuns.length
  await ui.press({ key: 'az-review' })
  expect(w.opened).toEqual(['agentzero-review'])
  expect(w.snapshotRuns.length).toBe(before + 1)
})

test('no band outside a workspace or during a survey', async ($, on) => {
  const w = world(on, { existing: [] })
  await $.session.start(START)
  await $.ui.mount({ plugin: 'agentzero', surface: 'desktop', component: 'AbovePrompt', props: BAND })
  expect(w.engineDrew).toEqual(['AbovePrompt'])
  w.existing.add('/w/System.md')
  await $.ui.mount({ plugin: 'agentzero', surface: 'desktop', component: 'AbovePrompt', props: { ...BAND, hasSurvey: true } })
  expect(w.engineDrew).toEqual(['AbovePrompt', 'AbovePrompt'])
})

test('no ring when usage has no percent', async ($, on) => {
  const w = world(on)
  w.contextPercent = undefined
  await $.session.start(START)
  const ui = await $.ui.mount({ plugin: 'agentzero', surface: 'desktop', component: 'AbovePrompt', props: BAND })
  expect(await bandSource(ui)).not.toContain('上下文')
})

test('a failed hot set shows red in the band', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  w.setRun({ exitCode: 1, stdout: '' })
  await $.prompt.submit(PROMPT('one'))
  const ui = await $.ui.mount({ plugin: 'agentzero', surface: 'desktop', component: 'AbovePrompt', props: BAND })
  expect(await bandSource(ui)).toContain('hot set 未加载（exit 1）')
})

test('/agentzero review opens the pane', async ($, on) => {
  const w = world(on)
  await $.session.start(START)
  const out = await $.command.run({ command: 'agentzero', args: 'review' })
  expect(out.text).toBe('已打开 AgentZero 待确认面板。')
  expect(w.opened).toEqual(['agentzero-review'])
})

test('/agentzero review outside a workspace opens nothing', async ($, on) => {
  const w = world(on, { existing: [] })
  const out = await $.command.run({ command: 'agentzero', args: 'review' })
  expect(out.text).toContain('not inside an AgentZero workspace')
  expect(w.opened).toEqual([])
})

async function mountPane($: any) {
  return $.ui.mount({ plugin: 'agentzero', surface: 'desktop', component: 'Pane', props: PANE, requestId: 'agentzero-review' })
}

async function sources(ui: any): Promise<string[]> {
  return (await ui.findAll({ type: 'Svg' })).map((s: any) => String(s.props.source))
}

test('the pane lists what waits, with keep and reject', async ($, on) => {
  world(on)
  await $.session.start(START)
  const ui = await mountPane($)
  const svgs = await sources(ui)
  expect(svgs.length).toBe(2)
  expect(svgs[0]).toContain('1 条待确认')
  expect(svgs[1]).toContain('周五不部署')
  expect(await ui.find({ key: 'az-keep-fact:a' })).toBeDefined()
  expect(await ui.find({ key: 'az-reject-fact:a' })).toBeDefined()
})

test('keep runs the kernel and marks the item kept', async ($, on) => {
  const w = world(on)
  w.responder = () => ({ exitCode: 0, stdout: 'confirmed: fact:a — 周五不部署\n' })
  await $.session.start(START)
  const ui = await mountPane($)
  w.snapshotJson = EMPTY
  await ui.press({ key: 'az-keep-fact:a' })
  expect(w.runs.at(-1)).toEqual({ argv: ['/w/a0', 'memory', 'review', '--confirm', 'fact:a'], init: { cwd: '/w', timeoutMs: 10000 } })
  const svgs = await sources(ui)
  expect(svgs[0]).toContain('1 条已处理')
  expect(svgs[1]).toContain('✓ 已保留')
  expect(await ui.find({ key: 'az-keep-fact:a' })).toBeUndefined()
})

test("a keep that fails shows the kernel's first error line and keeps the buttons", async ($, on) => {
  const w = world(on)
  w.responder = () => ({ exitCode: 1, stderr: 'No pending item fact:a\nmore' })
  await $.session.start(START)
  const ui = await mountPane($)
  await ui.press({ key: 'az-keep-fact:a' })
  expect((await sources(ui))[1]).toContain('No pending item fact:a')
  expect(await ui.find({ key: 'az-keep-fact:a' })).toBeDefined()
})

test('a keep on an item handled elsewhere shows the error, not all clear', async ($, on) => {
  const w = world(on)
  w.responder = () => ({ exitCode: 1, stderr: 'no item waiting for confirmation with id fact:a' })
  await $.session.start(START)
  const ui = await mountPane($)
  w.snapshotJson = EMPTY
  await ui.press({ key: 'az-keep-fact:a' })
  expect((await sources(ui)).join('')).toContain('no item waiting for confirmation')
  expect(await ui.find({ text: '没有等你确认的东西 ✓' })).toBeUndefined()
  expect(await ui.find({ key: 'az-keep-fact:a' })).toBeUndefined()
})

test('with no snapshot the pane says why, not all clear', async ($, on) => {
  const w = world(on)
  w.snapshotJson = 'not json'
  await $.session.start(START)
  const ui = await mountPane($)
  expect(await ui.find({ text: '记忆状态读取失败（unreadable snapshot）' })).toBeDefined()
  expect(await ui.find({ text: '没有等你确认的东西 ✓' })).toBeUndefined()
})
