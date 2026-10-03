import type { On } from 'claude-code'
import { hintsFrom, hotSetContext, needsHotSet } from './hotset'
import { recordOperatorPrompt } from './feature-said'
import { locateWorkspace, sessionData } from './session'

const A0_TIMEOUT_MS = 10_000

function localTime(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function registerHotSet(on: On): void {
  on('session.start', async ($, e, next) => {
    const data = sessionData(await $.session.id())
    const exists = (p: string) => $.fs.stat(p).then(() => true, () => false)
    await locateWorkspace(data, () => $.session.root(), exists)
    return next(e)
  })

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
    recordOperatorPrompt(data, e)
    const exists = (p: string) => $.fs.stat(p).then(() => true, () => false)
    const workspace = await locateWorkspace(data, () => $.session.root(), exists)
    const now = await $.clock.now()
    if (workspace === null || !needsHotSet(data.inject, now)) return next(e)

    const a0 = workspace + '/a0'
    const fail = (reason: string) => {
      // the desktop app draws no status row, so the message also goes to a toast
      const text = `AgentZero: hot set not loaded (${reason})`
      $.ui.status(text)
      $.ui.toast(text)
      return next(e)
    }
    if (!(await exists(a0))) return fail('a0 not found')

    let ran
    try {
      ran = await $.process.run(
        [a0, 'memory', 'hot-set', '--scope', 'project', '--hints', hintsFrom(e.text)],
        { cwd: workspace, timeoutMs: A0_TIMEOUT_MS },
      )
    } catch (err) {
      return fail(/time/i.test(String((err as Error)?.message ?? err)) ? 'timed out' : 'could not run')
    }
    if (ran.exitCode !== 0) return fail(`exit ${ran.exitCode}`)
    if (ran.stdout.trim() === '') return fail('no output')

    data.inject = { lastAt: now, resetSince: false }
    return next({
      ...e,
      context: [...(e.context ?? []), hotSetContext(ran.stdout.trimEnd(), localTime(now))],
    })
  })
}
