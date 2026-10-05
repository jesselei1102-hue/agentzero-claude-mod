import { atom, read, update } from 'claude-code'
import type { On } from 'claude-code'
import type { HudState, PaneResults, PendingItem, RawOpen } from '../types'
import { bandModel } from './band'
import { cardForCall, groupCard, type CallLike } from './cards'
import { KIND_LABEL, REVIEW_PANE, REVIEW_TITLE, mergeResult, paneResult, paneRows, reviewArgv } from './pane'
import { locateWorkspace, sessionData, writeMarks } from './session'
import { EMPTY_HUD, refreshJob, type HudIo } from './snapshot'
import { MUTED, PALETTE, bandSvg, cardSvg, paneHeaderSvg, pendingItemSvg } from './svg'

const hudAtom = atom({ plugin: 'agentzero', key: 'hud' } as const, EMPTY_HUD as HudState)
const hotSetErrorAtom = atom({ plugin: 'agentzero', key: 'hotSetError' } as const, null as string | null)
const paneResultsAtom = atom({ plugin: 'agentzero', key: 'paneResults' } as const, {} as PaneResults)
const rawOpenAtom = atom({ plugin: 'agentzero', key: 'rawOpen' } as const, {} as RawOpen)

const KEEP_TIMEOUT_MS = 10_000

function field(value: unknown, key: string): string {
  const v = typeof value === 'object' && value !== null ? (value as Record<string, unknown>)[key] : undefined
  return typeof v === 'string' ? v : ''
}

// What "原始命令" shows: the command and its output for Bash, the path for a Read.
function rawText(call: CallLike): string {
  if (call.tool === 'Read') return field(call.input, 'file_path')
  return `$ ${field(call.input, 'command')}\n${field(call.output, 'stdout')}`.trimEnd()
}

export function registerHud(on: On): void {
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const data = sessionData(await $.session.id())
    const workspace = await locateWorkspace(data, () => $.session.root(), p => $.fs.stat(p).then(() => true, () => false))
    if (workspace === null) return next(e)

    let percent: number | undefined
    try {
      percent = (await $.session.usage()).context.percent
    } catch {
      percent = undefined
    }
    const m = bandModel(await read($, hudAtom), await read($, hotSetErrorAtom), percent, await $.clock.now())
    const openReview = async () => {
      await $.ui.open({ id: REVIEW_PANE, title: REVIEW_TITLE })
      const io: HudIo = {
        run: (argv, init) => $.process.run(argv, init),
        read: p => $.fs.read(p) as Promise<string>,
        write: fn => update($, hudAtom, fn),
        status: t => $.ui.status(t),
        pluginRoot: $.plugin.root,
      }
      await data.gate.run(refreshJob(io, workspace))
    }
    const { Box, Text, Button, Svg } = $.ui.resolve(e) as Record<string, (props: Record<string, unknown>) => never>
    const review = m.showReview ? <Button key="az-review" label="查看待确认" variant="primary" onPress={openReview} /> : null

    if (e.surface === 'terminal') {
      return (
        <Box flexDirection="row" gap={1}>
          {m.pills.map(p => (
            <Text color={PALETTE[p.tone].fg} backgroundColor={PALETTE[p.tone].bg}>{` ${p.text} `}</Text>
          ))}
          {m.ring !== null && (
            <Text color={MUTED}>{`上下文 ${m.ring.percent}%${m.ring.note !== null ? ` · ${m.ring.note}` : ''}`}</Text>
          )}
          {review}
        </Box>
      )
    }
    return (
      <Box flexDirection="row" alignItems="center" gap={1}>
        <Svg source={bandSvg(m)} alt={m.alt} />
        {review}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: REVIEW_PANE }, async ($, e) => {
    const { Box, Text, Button, Svg } = $.ui.resolve(e) as Record<string, (props: Record<string, unknown>) => never>
    const data = sessionData(await $.session.id())
    const workspace = await locateWorkspace(data, () => $.session.root(), p => $.fs.stat(p).then(() => true, () => false))
    if (workspace === null) return <Text color={MUTED}>这里不是 AgentZero 工作区。</Text>

    const hud = await read($, hudAtom)
    if (hud.snapshot === null) {
      // never "nothing waits" when the state could not be read
      return <Text color={MUTED}>{hud.error !== null ? `记忆状态读取失败（${hud.error}）` : '记忆读取中…'}</Text>
    }
    const { rows, open, done } = paneRows(hud.snapshot?.pending ?? [], await read($, paneResultsAtom))
    const decide = async (item: PendingItem, verb: 'keep' | 'reject') => {
      let ran
      try {
        ran = await $.process.run(reviewArgv(workspace, verb, item.id), { cwd: workspace, timeoutMs: KEEP_TIMEOUT_MS })
      } catch (err) {
        ran = err instanceof Error ? err : new Error(String(err))
      }
      const result = paneResult(item, verb, ran)
      await update($, paneResultsAtom, m => mergeResult(m, result))
      const io: HudIo = {
        run: (argv, init) => $.process.run(argv, init),
        read: p => $.fs.read(p) as Promise<string>,
        write: fn => update($, hudAtom, fn),
        status: t => $.ui.status(t),
        pluginRoot: $.plugin.root,
      }
      await data.gate.run(refreshJob(io, workspace))
    }
    const buttons = (item: PendingItem) => (
      <Box flexDirection="row" gap={2}>
        <Button key={`az-keep-${item.id}`} label="✓ 保留" plain={true} onPress={() => decide(item, 'keep')} />
        <Button key={`az-reject-${item.id}`} label="✗ 拒绝" plain={true} dimColor={true} onPress={() => decide(item, 'reject')} />
      </Box>
    )
    const empty = rows.length === 0 ? <Text color={PALETTE.green.fg}>没有等你确认的东西 ✓</Text> : null

    if (e.surface === 'terminal') {
      return (
        <Box flexDirection="column" gap={1}>
          <Text bold={true}>{`待你确认 · ${open} 条待确认 · ${done} 条已处理`}</Text>
          {rows.map(row => (
            <Box flexDirection="column">
              <Text>{`[${KIND_LABEL[row.item.kind] ?? row.item.kind}] ${row.item.sentence}`}</Text>
              {row.state === 'kept' && <Text color={PALETTE.green.fg}>✓ 已保留</Text>}
              {row.state === 'rejected' && <Text color={MUTED}>✗ 已拒绝</Text>}
              {row.state === 'failed' && <Text color={PALETTE.red.fg}>{row.message ?? ''}</Text>}
              {row.actionable && buttons(row.item)}
            </Box>
          ))}
          {empty}
        </Box>
      )
    }
    return (
      <Box flexDirection="column" gap={1} paddingX={1}>
        <Svg source={paneHeaderSvg(open, done)} alt={`${open} 条待确认，${done} 条已处理`} />
        {rows.map(row => (
          <Box flexDirection="column" gap={0}>
            <Svg source={pendingItemSvg(row)} alt={row.item.sentence} />
            {row.actionable && buttons(row.item)}
          </Box>
        ))}
        {empty}
      </Box>
    )
  })

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const data = sessionData(await $.session.id())
    const workspace = await locateWorkspace(data, () => $.session.root(), p => $.fs.stat(p).then(() => true, () => false))
    if (workspace === null) return next(e)
    const call: CallLike = e.props
    const card = cardForCall(call, workspace, writeMarks)
    if (card === null) return next(e)

    const id = e.props.tool_use_id
    const open = (await read($, rawOpenAtom))[id] === true
    const { Box, Text, Button, Code, Svg } = $.ui.resolve(e) as Record<string, (props: Record<string, unknown>) => never>
    const toggle = (
      <Button key={`az-raw-${id}`} label={open ? '收起' : '原始命令'} plain={true} dimColor={true}
        onPress={() => update($, rawOpenAtom, m => ({ ...m, [id]: !open }))} />
    )
    const raw = open ? <Code language="bash" source={rawText(call)} /> : null
    if (e.surface === 'terminal') {
      return (
        <Box flexDirection="column">
          <Text bold={true} color={PALETTE[card.tone].fg}>{`${card.icon} ${card.label} · ${card.title}`}</Text>
          {card.detail !== null && <Text color={MUTED}>{card.detail}</Text>}
          {toggle}
          {raw}
        </Box>
      )
    }
    return (
      <Box flexDirection="column">
        <Svg source={cardSvg(card)} alt={`${card.label}：${card.title}`} />
        {toggle}
        {raw}
      </Box>
    )
  })

  // A folded group hides the cards inside it. The terminal draws a group open when asked;
  // the desktop ignores that (probe, 2026-10-06) but shows a tree the plugin draws under its
  // own fold header, so there the group draws its cards itself.
  on('ui.render', { component: 'ToolGroup' }, async ($, e, next) => {
    if (e.props.isExpanded) return next(e)
    const data = sessionData(await $.session.id())
    const workspace = await locateWorkspace(data, () => $.session.root(), p => $.fs.stat(p).then(() => true, () => false))
    if (workspace === null) return next(e)
    if (e.surface === 'terminal') {
      const done = e.props.calls.some(call => cardForCall(call, workspace, writeMarks) !== null)
      return done ? next({ ...e, props: { ...e.props, isExpanded: true } }) : next(e)
    }
    const cards = e.props.calls.map(call => groupCard(call, workspace, writeMarks)).filter(card => card !== null)
    if (cards.length === 0) return next(e)
    const { Box, Text, Svg } = $.ui.resolve(e) as Record<string, (props: Record<string, unknown>) => never>
    const others = e.props.calls.length - cards.length
    return (
      <Box flexDirection="column" gap={1}>
        {cards.map(card => (
          <Svg source={cardSvg(card)} alt={`${card.label}：${card.title}`} />
        ))}
        {others > 0 && <Text color={MUTED}>{`另有 ${others} 条命令`}</Text>}
      </Box>
    )
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === REVIEW_PANE) await update($, paneResultsAtom, () => ({}))
    return next(e)
  })
}
