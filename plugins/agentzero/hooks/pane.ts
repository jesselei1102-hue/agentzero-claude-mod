import type { PaneResult, PaneResults, PendingItem } from '../types'
import type { RunResult } from './snapshot'

export const REVIEW_PANE = 'agentzero-review'
export const REVIEW_TITLE = 'AgentZero · Review'

export type PaneItemState = 'open' | 'kept' | 'rejected' | 'failed'
// actionable: the item still waits, so keep and reject can still be pressed.
export type PaneRow = { item: PendingItem; state: PaneItemState; message: string | null; actionable: boolean }

export const KIND_LABEL: Record<string, string> = { fact: 'Fact', episode: 'Episode', entity: 'Entity', edge: 'Edge', skill: 'Skill' }

export function paneRows(pending: readonly PendingItem[], results: PaneResults): { rows: PaneRow[]; open: number; done: number } {
  const rows: PaneRow[] = pending.map(item => {
    const r = results[item.id]
    if (r === undefined) return { item, state: 'open', message: null, actionable: true }
    const failed = r.outcome === 'failed'
    return { item, state: r.outcome, message: failed ? r.message : null, actionable: failed }
  })
  // An item decided here, or one whose press failed because it was decided elsewhere, stays
  // listed after it leaves the snapshot, so the pane never hides what happened to it.
  const listed = new Set(pending.map(p => p.id))
  for (const r of Object.values(results)) {
    if (!listed.has(r.item.id)) {
      rows.push({ item: r.item, state: r.outcome, message: r.outcome === 'failed' ? r.message : null, actionable: false })
    }
  }
  return {
    rows,
    open: rows.filter(r => r.actionable).length,
    done: Object.values(results).filter(r => r.outcome !== 'failed').length,
  }
}

// A press that fails after one that succeeded (a double press) must not hide the decision.
export function mergeResult(results: PaneResults, result: PaneResult): PaneResults {
  const prev = results[result.item.id]
  if (result.outcome === 'failed' && prev !== undefined && prev.outcome !== 'failed') return results
  return { ...results, [result.item.id]: result }
}

export function reviewArgv(workspace: string, verb: 'keep' | 'reject', id: string): string[] {
  return [`${workspace}/a0`, 'memory', 'review', verb === 'keep' ? '--confirm' : '--reject', id]
}

function firstLine(text: string): string {
  return text.split('\n').map(l => l.trim()).find(l => l !== '') ?? ''
}

export function paneResult(item: PendingItem, verb: 'keep' | 'reject', ran: RunResult | Error): PaneResult {
  if (ran instanceof Error) {
    return { item, outcome: 'failed', message: /time/i.test(ran.message) ? 'timed out' : 'could not run' }
  }
  if (ran.exitCode === 0) return { item, outcome: verb === 'keep' ? 'kept' : 'rejected', message: '' }
  return { item, outcome: 'failed', message: firstLine(ran.stderr) || firstLine(ran.stdout) || `exit ${ran.exitCode}` }
}
