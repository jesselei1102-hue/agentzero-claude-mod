import type { On, SessionMessage } from 'claude-code'
import { mock } from 'claude-code/testing'

// The engine stands beneath the plugin in a test: this answers every call the hot-set
// feature makes, and records what the plugin did.
export type World = {
  statuses: (string | undefined)[]
  toasts: string[]
  runs: { argv: readonly string[]; init: unknown }[]
  contexts: (readonly string[] | undefined)[]
  clock: ReturnType<typeof mock.clock>
  setRun: (answer: { exitCode: number; stdout: string; stderr?: string } | Error) => void
  responder?: (argv: readonly string[]) => { exitCode: number; stdout?: string; stderr?: string }
  registered: string[]
  existing: Set<string>
  messages: SessionMessage[]
  commands: string[]
  toolUseIds: (string | undefined)[]
  denyBash: boolean
  snapshotJson: string
  snapshotRuns: { argv: readonly string[]; init: unknown }[]
  contextPercent: number | undefined
  opened: string[]
  engineDrew: string[]
  groupExpanded: boolean[]
}

export const SNAPSHOT = {
  schema: 1,
  active: 3,
  pending: [{ id: 'fact:a', kind: 'fact', sentence: '周五不部署', provenance: 'agent proposed it', createdAt: '2026-10-04T10:49:18+08:00' }],
  hotSet: { at: '2026-10-05T09:57:00+08:00', factIds: [] },
}

export function world(
  on: On,
  opts: { root?: string; existing?: string[]; env?: Record<string, string>; files?: Record<string, string> } = {},
): World {
  const env = opts.env ?? { HOME: '/home/u' }
  const files: Record<string, string> = { '/memory/traces/a0.python': '/usr/bin/python3\n', ...opts.files }
  const root = opts.root ?? '/w'
  const w: World = {
    statuses: [],
    toasts: [],
    runs: [],
    contexts: [],
    clock: mock.clock(on, { now: 1_000_000 }),
    setRun: answer => {
      next = answer
    },
    messages: [],
    registered: [],
    commands: [],
    toolUseIds: [],
    denyBash: false,
    snapshotJson: JSON.stringify(SNAPSHOT),
    snapshotRuns: [],
    contextPercent: 41,
    opened: [],
    engineDrew: [],
    groupExpanded: [],
    existing: new Set(opts.existing ?? [`${root}/System.md`, `${root}/memory`, `${root}/a0`]),
  }
  let next: { exitCode: number; stdout: string; stderr?: string } | Error = { exitCode: 0, stdout: '## Facts (1)\n' }

  on('session.id', async () => ({ value: 's1' }))
  on('session.root', async () => ({ value: root }))
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('command.register', async (_$, e) => {
    w.registered.push(e.name)
    return { value: { command: e.name } }
  })
  on('env.get', async (_$, e) => ({ value: env[e.name] }))
  on('fs.read', async (_$, e) => (() => {
    const key = Object.keys(files).find(k => e.path.endsWith(k))
    return key !== undefined ? { value: files[key] } : { deny: 'ENOENT' }
  })())
  on('session.compact', async () => ({ messages: [MSG] }))
  on('session.end', async (_$, e) => ({ sessionId: e.sessionId }))
  on('prompt.submit', async (_$, e) => {
    w.contexts.push(e.context)
    return { text: e.text }
  })
  on('fs.stat', async (_$, e) =>
    w.existing.has(e.path)
      ? { value: { kind: 'file' as const, size: 0, mtimeMs: 0, isLink: false } }
      : { deny: 'ENOENT' },
  )
  on('process.run', async (_$, e) => {
    if (String(e.argv[1] ?? '').endsWith('/tools/snapshot.py')) {
      w.snapshotRuns.push({ argv: e.argv, init: e.init })
      return { value: { exitCode: 0, stdout: w.snapshotJson, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    w.runs.push({ argv: e.argv, init: e.init })
    if (w.responder !== undefined) {
      const r = w.responder(e.argv)
      return {
        value: { exitCode: r.exitCode, stdout: r.stdout ?? '', stderr: r.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false },
      }
    }
    if (next instanceof Error) return { deny: next.message }
    return {
      value: {
        exitCode: next.exitCode,
        stdout: next.stdout,
        stderr: next.stderr ?? '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  on('session.messages', async () => ({ value: w.messages }))
  on('tool.call', { tool: 'Bash' }, async (_$, e) => {
    w.commands.push(e.command)
    w.toolUseIds.push(e.tool_use_id)
    if (w.denyBash) return { deny: 'denied' }
    return { result: { stdout: 'ok', stderr: '' } }
  })
  on('session.usage', async () => ({
    value: { startedAt: 0, context: { window: 200_000, percent: w.contextPercent }, rateLimits: [] },
  }))
  on('ui.open', async (_$, e) => {
    w.opened.push(e.id)
    return { value: { isPlaced: true as const } }
  })
  on('ui.close', async () => ({ value: undefined }))
  for (const component of ['AbovePrompt', 'Pane', 'ToolUse', 'ToolGroup'] as const) {
    on('ui.render', { component }, async (_$, e) => {
      w.engineDrew.push(component)
      if (e.component === 'ToolGroup') w.groupExpanded.push(e.props.isExpanded)
      const { Text } = _$.ui.resolve(e)
      return Text({ children: 'engine' } as never)
    })
  }
  on('ui.status', async (_$, e) => {
    w.statuses.push(e.text)
  })
  on('ui.toast', async (_$, e) => {
    w.toasts.push(e.text)
  })
  return w
}

export const MSG = { role: 'user' as const, text: 'summary', toolUses: [] }
export const START = { cwd: '/w', surface: 'terminal' as const, isInteractive: true }
export const PROMPT = (text: string) => ({ text, origin: { kind: 'composer' as const }, wait: false })
