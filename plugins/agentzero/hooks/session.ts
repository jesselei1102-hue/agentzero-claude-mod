import type { InjectState } from './hotset'
import { RefreshGate } from './snapshot'
import { findWorkspace, type Probe } from './workspace'

export type WriteMark = 'rewritten' | 'unchecked'

// The word check's verdict on a Bash call, by tool_use_id, for the card drawn later.
export const writeMarks = new Map<string, WriteMark>()

export type SessionData = {
  workspace: string | null
  located: boolean
  inject: InjectState
  prompts: string[]
  seeded: boolean
  gate: RefreshGate
}

const sessions = new Map<string, SessionData>()

export function sessionData(id: string): SessionData {
  let data = sessions.get(id)
  if (data === undefined) {
    data = {
      workspace: null,
      located: false,
      inject: { lastAt: null, resetSince: false },
      prompts: [],
      seeded: false,
      gate: new RefreshGate(),
    }
    sessions.set(id, data)
  }
  return data
}

export function forgetSession(id: string): void {
  sessions.delete(id)
}

// A /clear moves the process to a new session id without a session.start, so the
// workspace is found the first time a hook needs it for an id, not only at start.
// `$` never crosses an import, so the caller passes the two lookups as closures.
export async function locateWorkspace(
  data: SessionData,
  root: () => Promise<string>,
  exists: Probe,
): Promise<string | null> {
  if (!data.located) {
    data.workspace = await findWorkspace(await root(), exists)
    data.located = true
  }
  return data.workspace
}
