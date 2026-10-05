import { atom, update } from 'claude-code'
import type { On } from 'claude-code'
import type { HudState } from '../types'
import { isMemoryWrite } from './cards'
import { EMPTY_HUD, refreshJob, type HudIo } from './snapshot'
import { locateWorkspace, sessionData, writeMarks, type SessionData } from './session'
import { parseRemember, proposeCommand, saidFound } from './words'

const hudAtom = atom({ plugin: 'agentzero', key: 'hud' } as const, EMPTY_HUD as HudState)

const OPERATOR_ORIGINS = ['composer', 'bridge', 'sdk']

const DOWNGRADE_NOTE =
  'AgentZero plugin: the --said words were not found in what the operator typed in this session, so this was recorded as a proposal. Ask the operator.'
const UNCHECKED = "AgentZero: the operator's words in this remember were not checked"

// The engine allows one `prompt.submit` hook per plugin without a matcher, so the one in
// feature-hotset.ts calls this for every prompt.
export function recordOperatorPrompt(data: SessionData, e: { text: string; origin?: { kind: string } }): void {
  if (e.origin !== undefined && OPERATOR_ORIGINS.includes(e.origin.kind)) data.prompts.push(e.text)
}

type Row = { role: string; text: string; toolResults?: readonly unknown[] }

// Rows the engine writes as `user` that are not words the operator typed: the summary a
// compaction leaves behind (it can hold the agent's own paraphrase) and the records of
// slash commands.
const NOT_TYPED = /^(This session is being continued from a previous conversation|<local-command-|<command-name>)/

// After a resume the operator's earlier prompts are in the transcript, not in this
// process. Called with the main conversation's rows at the first prompt of the process.
export function seedFromRows(data: SessionData, rows: readonly Row[]): void {
  for (const row of rows) {
    const typed = row.role === 'user' && (row.toolResults === undefined || row.toolResults.length === 0)
    if (typed && !NOT_TYPED.test(row.text.trimStart())) data.prompts.push(row.text)
  }
  data.seeded = true
}

export function registerSaidCheck(on: On): void {
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const data = sessionData(await $.session.id())
    const exists = (p: string) => $.fs.stat(p).then(() => true, () => false)
    const workspace = await locateWorkspace(data, () => $.session.root(), exists)
    if (workspace === null) return next(e)

    const ran = await checkWords()
    if (isMemoryWrite(e.command) && ran.deny === undefined) {
      const io: HudIo = {
        run: (argv, init) => $.process.run(argv, init),
        read: p => $.fs.read(p) as Promise<string>,
        write: fn => update($, hudAtom, fn),
        status: t => $.ui.status(t),
        pluginRoot: $.plugin.root,
      }
      await data.gate.run(refreshJob(io, workspace))
    }
    return ran

    async function checkWords() {
      const parsed = parseRemember(e.command)
      if (parsed.kind === 'none') return next(e)
      if (parsed.kind === 'unreadable') {
        writeMarks.set(e.tool_use_id, 'unchecked')
        // the desktop app draws no status row, so the message also goes to a toast
        $.ui.status(UNCHECKED)
        $.ui.toast(UNCHECKED)
        return next(e)
      }

      // Normally seeded at the first prompt (feature-hotset.ts); this covers a module
      // reloaded mid-session. Always the main conversation: a subagent's remember is the
      // main operator's words too.
      if (!data.seeded) {
        try {
          seedFromRows(data, await $.session.messages({}))
        } catch {
          // checked against what this process saw; tried again at the next remember
        }
      }

      if (saidFound(parsed.call.said, data.prompts)) return next(e)

      writeMarks.set(e.tool_use_id, 'rewritten')
      const rewritten = await next({ ...e, command: proposeCommand(parsed.call) })
      if (rewritten.deny !== undefined) return rewritten
      return { ...rewritten, context: [...(rewritten.context ?? []), DOWNGRADE_NOTE] }
    }
  })
}
