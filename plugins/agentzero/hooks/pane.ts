import type { PaneResult, PaneResults, PendingItem } from '../types'
import type { RunResult } from './snapshot'

export const REVIEW_PANE = 'agentzero-review'
export const REVIEW_TITLE = 'AgentZero · 待确认'

export type PaneItemState = 'open' | 'kept' | 'rejected' | 'failed'
export type PaneRow = { item: PendingItem; state: PaneItemState; message: string | null }

export const KIND_LABEL: Record<string, string> = { fact: 'Fact', episode: 'Episode', entity: '实体', edge: '关系', skill: '技能' }

export function paneRows(pending: readonly PendingItem[], results: PaneResults): { rows: PaneRow[]; open: number; done: number } {
  const rows: PaneRow[] = pending.map(item => {
    const r = results[item.id]
    if (r === undefined) return { item, state: 'open', message: null }
    return { item, state: r.outcome, message: r.outcome === 'failed' ? r.message : null }
  })
  const listed = new Set(pending.map(p => p.id))
  for (const r of Object.values(results)) {
    if (r.outcome !== 'failed' && !listed.has(r.item.id)) rows.push({ item: r.item, state: r.outcome, message: null })
  }
  return {
    rows,
    open: rows.filter(r => r.state === 'open' || r.state === 'failed').length,
    done: Object.values(results).filter(r => r.outcome !== 'failed').length,
  }
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
