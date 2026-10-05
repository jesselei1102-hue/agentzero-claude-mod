import { atom, update } from 'claude-code'
import type { On } from 'claude-code'
import type { HudState } from '../types'
import { EMPTY_HUD, refreshJob, type HudIo } from './snapshot'
import { locateWorkspace, sessionData } from './session'
import { PYTHON_PROBE, findPython } from './python'
import { REVIEW_PANE, REVIEW_TITLE } from './pane'
import { findWorkspace } from './workspace'

const USAGE = [
  'Usage: /agentzero <init|upgrade|status|review>',
  '  init     make this project folder an AgentZero workspace for Claude Code',
  '  upgrade  bring this workspace to the plugin\'s AgentZero version',
  '  status   show whether this workspace can run, and the plugin and kernel versions',
  '  review   open the pane of what waits for your yes',
].join('\n')

const NO_PYTHON = [
  'AgentZero needs Python 3.11 or newer with PyYAML, and none was found',
  `(tried python3, python and the usual install folders; the check is: python3 -c "${PYTHON_PROBE}").`,
  'Install PyYAML with:',
  '  python3 -m pip install pyyaml',
  'then run the command again.',
].join('\n')

const PROBE_TIMEOUT_MS = 10_000
const KERNEL_TIMEOUT_MS = 120_000

function trimSlash(path: string): string {
  return path.length > 1 ? path.replace(/\/+$/, '') : path
}

// Why `init` must not run in this folder, or null when it may.
export function initRefusal(root: string, home: string | undefined, workspace: string | null): string | null {
  const dir = trimSlash(root)
  if (dir === '/') {
    return `AgentZero was not set up: ${dir} is the filesystem root. Open a project folder and run /agentzero init there.`
  }
  if (home !== undefined && dir === trimSlash(home)) {
    return `AgentZero was not set up: ${dir} is your home folder. Open a project folder and run /agentzero init there.`
  }
  if (workspace !== null) {
    return workspace === dir
      ? `AgentZero was not set up: ${dir} is already an AgentZero workspace. Use /agentzero upgrade or /agentzero status.`
      : `AgentZero was not set up: ${dir} is inside the AgentZero workspace ${workspace}. Open a project folder outside it and run /agentzero init there.`
  }
  return null
}

function shown(ran: { exitCode: number; stdout: string; stderr: string }): string {
  return [ran.stdout.trimEnd(), ran.stderr.trimEnd()].filter(s => s !== '').join('\n')
}

const hudAtom = atom({ plugin: 'agentzero', key: 'hud' } as const, EMPTY_HUD as HudState)

export function registerCommand(on: On): void {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'agentzero',
      description: 'Set up, upgrade, check or review AgentZero in this project (init, upgrade, status, review)',
      argumentHint: '<init|upgrade|status|review>',
    })
    const data = sessionData(await $.session.id())
    const workspace = await locateWorkspace(data, () => $.session.root(), p => $.fs.stat(p).then(() => true, () => false))
    if (workspace !== null) {
      const io: HudIo = {
        run: (argv, init) => $.process.run(argv, init),
        read: p => $.fs.read(p) as Promise<string>,
        write: fn => update($, hudAtom, fn),
        status: t => $.ui.status(t),
        pluginRoot: $.plugin.root,
      }
      await data.gate.run(refreshJob(io, workspace))
    }
    return next(e)
  })

  on('command.run', { command: 'agentzero' }, async ($, e) => {
    const sub = e.args.trim().split(/\s+/)[0] ?? ''
    if (sub !== 'init' && sub !== 'upgrade' && sub !== 'status' && sub !== 'review') return { text: USAGE }

    const root = trimSlash(await $.session.root())
    const exists = (p: string) => $.fs.stat(p).then(() => true, () => false)
    const workspace = await findWorkspace(root, exists)

    if (sub === 'init') {
      const refusal = initRefusal(root, await $.env.get('HOME'), workspace)
      if (refusal !== null) return { text: refusal }
    } else if (workspace === null) {
      return { text: `AgentZero: ${root} is not inside an AgentZero workspace. Run /agentzero init in a project folder first.` }
    }

    if (sub === 'review' && workspace !== null) {
      await $.ui.open({ id: REVIEW_PANE, title: REVIEW_TITLE })
      const data = sessionData(await $.session.id())
      const io: HudIo = {
        run: (argv, init) => $.process.run(argv, init),
        read: p => $.fs.read(p) as Promise<string>,
        write: fn => update($, hudAtom, fn),
        status: t => $.ui.status(t),
        pluginRoot: $.plugin.root,
      }
      await data.gate.run(refreshJob(io, workspace))
      return { text: '已打开 AgentZero 待确认面板。' }
    }

    const python = await findPython(argv => $.process.run(argv, { timeoutMs: PROBE_TIMEOUT_MS }))
    if (python === null) return { text: NO_PYTHON }

    const env = { PYTHONPATH: `${$.plugin.root}/kernel/src` }
    const kernel = async (argv: string[]) => {
      try {
        return await $.process.run([python, '-m', 'adapter', ...argv], { env, timeoutMs: KERNEL_TIMEOUT_MS })
      } catch (err) {
        return { exitCode: 1, stdout: '', stderr: String((err as Error)?.message ?? err) }
      }
    }

    if (sub === 'init') {
      const ran = await kernel(['init', root, '--harness', 'claude'])
      if (ran.exitCode !== 0) return { text: `AgentZero init failed (exit ${ran.exitCode}):\n${shown(ran)}` }
      return {
        text: `${shown(ran)}\nAgentZero is set up in ${root}. Start a new session here: the workspace's CLAUDE.md and hooks load when a session starts.`.trimStart(),
      }
    }

    // never --force: when the kernel stops on a file the operator edited, show its words as they are
    if (sub === 'upgrade') {
      const ran = await kernel(['materialize', workspace as string, '--harness', 'claude'])
      return { text: shown(ran) || `AgentZero upgrade finished (exit ${ran.exitCode}).` }
    }

    const ran = await kernel(['preflight', workspace as string])
    let versions = 'plugin and kernel versions unavailable'
    try {
      const plugin = JSON.parse(await $.fs.read(`${$.plugin.root}/.claude-plugin/plugin.json`)).version
      const source = JSON.parse(await $.fs.read(`${$.plugin.root}/kernel/SOURCE.json`))
      versions = `plugin ${plugin}, kernel ${source.version} (${String(source.commit).slice(0, 7)})`
    } catch {
      // the versions line says so
    }
    return { text: `${shown(ran)}\n${versions}`.trimStart() }
  })
}
