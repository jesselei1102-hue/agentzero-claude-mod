import { atom, read, update } from 'claude-code'
import type { On } from 'claude-code'
import type { HudState, PaneResults, PendingItem } from '../types'
import { bandModel } from './band'
import { KIND_LABEL, REVIEW_PANE, REVIEW_TITLE, paneResult, paneRows, reviewArgv } from './pane'
import { locateWorkspace, sessionData } from './session'
import { EMPTY_HUD, refreshJob, type HudIo } from './snapshot'
import { MUTED, PALETTE, bandSvg, paneHeaderSvg, pendingItemSvg } from './svg'

const hudAtom = atom({ plugin: 'agentzero', key: 'hud' } as const, EMPTY_HUD as HudState)
const hotSetErrorAtom = atom({ plugin: 'agentzero', key: 'hotSetError' } as const, null as string | null)
const paneResultsAtom = atom({ plugin: 'agentzero', key: 'paneResults' } as const, {} as PaneResults)

const KEEP_TIMEOUT_MS = 10_000

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
    const { rows, open, done } = paneRows(hud.snapshot?.pending ?? [], await read($, paneResultsAtom))
    const decide = async (item: PendingItem, verb: 'keep' | 'reject') => {
      let ran
      try {
        ran = await $.process.run(reviewArgv(workspace, verb, item.id), { cwd: workspace, timeoutMs: KEEP_TIMEOUT_MS })
      } catch (err) {
        ran = err instanceof Error ? err : new Error(String(err))
      }
      const result = paneResult(item, verb, ran)
      await update($, paneResultsAtom, m => ({ ...m, [item.id]: result }))
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
              {(row.state === 'open' || row.state === 'failed') && buttons(row.item)}
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
            {(row.state === 'open' || row.state === 'failed') && buttons(row.item)}
          </Box>
        ))}
        {empty}
      </Box>
    )
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === REVIEW_PANE) await update($, paneResultsAtom, () => ({}))
    return next(e)
  })
}
