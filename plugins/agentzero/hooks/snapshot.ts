import type { HudState, PendingItem, Snapshot } from '../types'
import { findPython } from './python'

export const SNAPSHOT_TIMEOUT_MS = 2_000
const PROBE_TIMEOUT_MS = 10_000

export const EMPTY_HUD: HudState = { snapshot: null, error: null, stale: false }

export type SnapshotResult = { ok: true; snapshot: Snapshot } | { ok: false; error: string }
export type RunInit = { cwd?: string; env?: Record<string, string>; timeoutMs?: number }
export type RunResult = { exitCode: number; stdout: string; stderr: string }
export type Run = (argv: string[], init: RunInit) => Promise<RunResult>

// `$` never crosses an import: the hook that refreshes builds these closures at its call site.
export type HudIo = {
  run: Run
  read: (path: string) => Promise<string>
  write: (fn: (prev: HudState) => HudState) => Promise<unknown>
  status: (text: string | undefined) => void
  pluginRoot: string
}

const UNREADABLE: SnapshotResult = { ok: false, error: 'unreadable snapshot' }

function isStr(v: unknown): v is string {
  return typeof v === 'string'
}

function pendingItem(v: unknown): PendingItem | null {
  if (typeof v !== 'object' || v === null) return null
  const o = v as Record<string, unknown>
  if (![o.id, o.kind, o.sentence, o.provenance].every(isStr)) return null
  if (o.createdAt !== null && !isStr(o.createdAt)) return null
  return { id: o.id as string, kind: o.kind as string, sentence: o.sentence as string, provenance: o.provenance as string, createdAt: o.createdAt as string | null }
}

export function parseSnapshot(stdout: string): SnapshotResult {
  let o: Record<string, unknown>
  try {
    const parsed: unknown = JSON.parse(stdout)
    if (typeof parsed !== 'object' || parsed === null) return UNREADABLE
    o = parsed as Record<string, unknown>
  } catch {
    return UNREADABLE
  }
  if (o.schema !== 1) return { ok: false, error: 'unknown snapshot schema' }
  if (isStr(o.error)) return { ok: false, error: o.error }
  if (typeof o.active !== 'number' || !Array.isArray(o.pending)) return UNREADABLE
  const pending = o.pending.map(pendingItem)
  if (pending.some(p => p === null)) return UNREADABLE
  let hotSet: Snapshot['hotSet'] = null
  if (o.hotSet !== null) {
    const h = o.hotSet as Record<string, unknown> | undefined
    if (typeof h !== 'object' || h === null) return UNREADABLE
    if (h.at !== null && !isStr(h.at)) return UNREADABLE
    if (!Array.isArray(h.factIds) || !h.factIds.every(isStr)) return UNREADABLE
    hotSet = { at: h.at as string | null, factIds: h.factIds as string[] }
  }
  return { ok: true, snapshot: { active: o.active, pending: pending as PendingItem[], hotSet } }
}

function firstLine(text: string): string {
  return text.split('\n').map(l => l.trim()).find(l => l !== '') ?? ''
}

const pythons = new Map<string, string>()

const NO_PYTHON = 'no usable Python 3.11 with PyYAML'

async function cachedPython(io: Pick<HudIo, 'read'>, workspace: string): Promise<string | null> {
  try {
    const cached = firstLine(await io.read(`${workspace}/memory/traces/a0.python`))
    return cached !== '' ? cached : null
  } catch {
    return null // ./a0 has not run here yet
  }
}

async function searchPython(io: Pick<HudIo, 'run'>, workspace: string): Promise<string | null> {
  const known = pythons.get(workspace)
  if (known !== undefined) return known
  const found = await findPython(argv => io.run(argv, { timeoutMs: PROBE_TIMEOUT_MS }))
  if (found !== null) pythons.set(workspace, found)
  return found
}

export async function readSnapshot(io: Pick<HudIo, 'run' | 'read' | 'pluginRoot'>, workspace: string): Promise<SnapshotResult> {
  const cached = await cachedPython(io, workspace)
  if (cached !== null) {
    const first = await runScript(io, cached, workspace)
    // ./a0 heals its own cache only when it next runs; until then, look for a Python here too
    if (first.ok || (first.error !== 'could not run' && first.error !== NO_PYTHON)) return first
  }
  const python = await searchPython(io, workspace)
  if (python === null || python === cached) return { ok: false, error: NO_PYTHON }
  return runScript(io, python, workspace)
}

async function runScript(io: Pick<HudIo, 'run' | 'pluginRoot'>, python: string, workspace: string): Promise<SnapshotResult> {
  let ran: RunResult
  try {
    ran = await io.run([python, `${io.pluginRoot}/tools/snapshot.py`, workspace], {
      cwd: workspace,
      env: { PYTHONPATH: `${workspace}/src` },
      timeoutMs: SNAPSHOT_TIMEOUT_MS,
    })
  } catch (err) {
    return { ok: false, error: /time/i.test(String((err as Error)?.message ?? err)) ? 'timed out' : 'could not run' }
  }
  if (ran.exitCode !== 0) return { ok: false, error: `exit ${ran.exitCode}: ${firstLine(ran.stderr)}` }
  return parseSnapshot(ran.stdout)
}

export function nextHud(prev: HudState, result: SnapshotResult): HudState {
  if (result.ok) return { snapshot: result.snapshot, error: null, stale: false }
  return { snapshot: prev.snapshot, error: result.error, stale: prev.snapshot !== null }
}

export function statusAfter(prev: HudState, result: SnapshotResult): string | undefined | null {
  if (!result.ok) return `AgentZero: 记忆状态读取失败（${result.error}）`
  return prev.error !== null ? undefined : null
}

export function refreshJob(io: HudIo, workspace: string): () => Promise<void> {
  return async () => {
    const result = await readSnapshot(io, workspace)
    let prev = EMPTY_HUD
    await io.write(p => {
      prev = p
      return nextHud(p, result)
    })
    const status = statusAfter(prev, result)
    if (status !== null) io.status(status)
  }
}

// One refresh at a time. A request during a run waits for one more run, made with the
// newest job, so a burst of writes costs at most one extra snapshot.
export class RefreshGate {
  private running: Promise<void> | null = null
  private waiting: { job: () => Promise<void>; done: Promise<void>; settle: () => void } | null = null

  run(job: () => Promise<void>): Promise<void> {
    if (this.running === null) return this.start(job)
    if (this.waiting !== null) {
      this.waiting.job = job
      return this.waiting.done
    }
    let settle = () => {}
    const done = new Promise<void>(r => {
      settle = r
    })
    this.waiting = { job, done, settle }
    return done
  }

  private start(job: () => Promise<void>): Promise<void> {
    const run = (async () => {
      try {
        await job()
      } catch {
        // a failed refresh keeps the last good snapshot; nothing to do here
      }
    })()
    this.running = run.then(() => {
      this.running = null
      const next = this.waiting
      this.waiting = null
      if (next !== null) void this.start(next.job).then(next.settle)
    })
    return run
  }
}
