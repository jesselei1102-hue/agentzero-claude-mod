import { atom, update } from 'claude-code'
import type { On } from 'claude-code'
import type { HudState } from '../types'
import { hintsFrom, hotSetContext, needsHotSet } from './hotset'
import { recordOperatorPrompt, seedFromRows } from './feature-said'
import { locateWorkspace, sessionData } from './session'
import { EMPTY_HUD, refreshJob, type HudIo } from './snapshot'

const hudAtom = atom({ plugin: 'agentzero', key: 'hud' } as const, EMPTY_HUD as HudState)
const hotSetErrorAtom = atom({ plugin: 'agentzero', key: 'hotSetError' } as const, null as string | null)

const A0_TIMEOUT_MS = 10_000

function localTime(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

type Loaded = { ok: true; output: string } | { ok: false; reason: string }

async function loadHotSet(
  workspace: string,
  prompt: string,
  exists: (path: string) => Promise<boolean>,
  run: (argv: string[], init: { cwd: string; timeoutMs: number }) => Promise<{ exitCode: number; stdout: string }>,
): Promise<Loaded> {
  const a0 = workspace + '/a0'
  if (!(await exists(a0))) return { ok: false, reason: 'a0 not found' }
  let ran
  try {
    ran = await run([a0, 'memory', 'hot-set', '--scope', 'project', '--hints', hintsFrom(prompt)], { cwd: workspace, timeoutMs: A0_TIMEOUT_MS })
  } catch (err) {
    return { ok: false, reason: /time/i.test(String((err as Error)?.message ?? err)) ? 'timed out' : 'could not run' }
  }
  if (ran.exitCode !== 0) return { ok: false, reason: `exit ${ran.exitCode}` }
  if (ran.stdout.trim() === '') return { ok: false, reason: 'no output' }
  return { ok: true, output: ran.stdout.trimEnd() }
}

export function registerHotSet(on: On): void {
  on('session.compact', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && e.trigger !== 'precompute' && result.skip === undefined) {
      sessionData(await $.session.id()).inject.resetSince = true
    }
    return result
  })

  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear') sessionData(e.sessionId).inject.resetSince = true
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    const data = sessionData(await $.session.id())
    if (!data.seeded) {
      // the transcript's earlier user rows, read before this prompt joins the list
      try {
        seedFromRows(data, await $.session.messages({}))
      } catch {
        // the first remember tries again
      }
    }
    recordOperatorPrompt(data, e)
    const exists = (p: string) => $.fs.stat(p).then(() => true, () => false)
    const workspace = await locateWorkspace(data, () => $.session.root(), exists)
    const now = await $.clock.now()
    if (workspace === null) return next(e)

    let out = e
    if (needsHotSet(data.inject, now)) {
      const loaded = await loadHotSet(workspace, e.text, exists, (argv, init) => $.process.run(argv, init))
      if (loaded.ok) {
        data.inject = { lastAt: now, resetSince: false }
        out = { ...e, context: [...(e.context ?? []), hotSetContext(loaded.output, localTime(now))] }
        await update($, hotSetErrorAtom, () => null)
      } else {
        // the desktop app draws no status row, so the message also goes to a toast
        const text = `AgentZero: hot set not loaded (${loaded.reason})`
        $.ui.status(text)
        $.ui.toast(text)
        await update($, hotSetErrorAtom, () => loaded.reason)
      }
    }

    const result = await next(out)
    const io: HudIo = {
      run: (argv, init) => $.process.run(argv, init),
      read: p => $.fs.read(p) as Promise<string>,
      write: fn => update($, hudAtom, fn),
      status: t => $.ui.status(t),
      pluginRoot: $.plugin.root,
    }
    await data.gate.run(refreshJob(io, workspace))
    return result
  })
}
