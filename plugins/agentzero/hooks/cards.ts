import type { WriteMark } from './session'
import { parseRemember, splitWords } from './words'

export type { WriteMark }
export type Tone = 'green' | 'amber' | 'grey' | 'blue'
export type Card = { icon: string; label: string; tone: Tone; title: string; detail: string | null; outline: boolean }
export type CallLike = {
  tool: string
  input: unknown
  output?: unknown
  isRunning: boolean
  isErrored: boolean
  isInterrupted: boolean
  tool_use_id?: string
}
type A0Command = { module: 'memory' | 'skills' | 'knowledge'; sub: string; args: string[] }

const MODULES = new Set(['memory', 'skills', 'knowledge'])
const ENV_ASSIGN = /^[A-Za-z_][A-Za-z0-9_]*=/

export function a0Command(command: string): A0Command | null {
  const t = splitWords(command)
  if (t === null) return null
  let i = t[0] === 'cd' && t[2] === '&&' ? 3 : 0
  while (i < t.length && ENV_ASSIGN.test(t[i])) i++
  let at: number
  if (/(^|\/)a0$/.test(t[i] ?? '')) at = i + 1
  else if (/(^|\/)python[0-9.]*$/.test(t[i] ?? '') && t[i + 1] === '-m') at = i + 2
  else return null
  const module = t[at]
  const sub = t[at + 1]
  if (!MODULES.has(module) || sub === undefined) return null
  return { module: module as A0Command['module'], sub, args: t.slice(at + 2) }
}

function writes(c: A0Command): boolean {
  if (c.module === 'memory') {
    if (['remember', 'propose', 'forget', 'link', 'promote'].includes(c.sub)) return true
    return c.sub === 'review' && c.args.some(a => a === '--confirm' || a === '--reject')
  }
  if (c.module === 'skills') return c.sub === 'draft'
  return c.sub === 'add'
}

export function isMemoryWrite(command: string): boolean {
  const c = a0Command(command)
  return c !== null && writes(c)
}

const LINE = /^(remembered|already remembered|proposed|forgot|confirmed|rejected|linked|drafted): (\S+) — (.+)$/
const ON_RECORD = /^already on record \((\w+)\): (\S+) — (.+)$/
const DECLARED = /^(already declared|declared): (\S+) \(([^)]*)\) — (.+?) — .*$/

const ON_FILE = '已在记录中'

function card(icon: string, label: string, tone: Tone, title: string, detail: string | null, outline = false): Card {
  return { icon, label, tone, title, detail, outline }
}

const remembered = (title: string, detail: string, outline = false) => card('📌', '已记住', 'green', title, detail, outline)
const waiting = (title: string, detail: string) => card('⏳', '待你确认', 'amber', title, detail)
const skill = (name: string) => card('🧭', '使用技能', 'blue', name, null)

export function cardForBash(command: string, stdout: string, mark: WriteMark | undefined): Card | null {
  // A command the word check marked is a remember even when it could not be read.
  const c = a0Command(command) ?? (mark !== undefined ? { module: 'memory' as const, sub: 'remember', args: [] } : null)
  if (c === null) return null
  if (c.module === 'skills' && c.sub === 'run') return skill(c.args[0] ?? '')
  if (!writes(c)) return null

  const first = stdout.split('\n')[0].trimEnd()
  const declared = DECLARED.exec(first)
  if (declared) return card('📚', '资料已加入', 'blue', declared[4], declared[1] === 'declared' ? declared[3] : ON_FILE)
  const onRecord = ON_RECORD.exec(first)
  if (onRecord) return onRecord[1] === 'active' ? remembered(onRecord[3], ON_FILE) : waiting(onRecord[3], ON_FILE)
  const m = LINE.exec(first)
  if (!m) return null
  const [, verb, id, text] = m
  switch (verb) {
    case 'remembered': {
      const parsed = parseRemember(command)
      if (mark === 'unchecked' || parsed.kind !== 'remember') return remembered(text, '引用未核对', true)
      return remembered(text, `你的原话 “${parsed.call.said}” ✓ 已核对`)
    }
    case 'already remembered':
      return remembered(text, ON_FILE)
    case 'proposed':
      if (mark === 'rewritten') return waiting(text, '引用不在你说过的话里，已改为提议')
      return waiting(text, c.sub === 'remember' ? '句子比你的原话多，已改为提议' : '助手推断，等你确认')
    case 'forgot':
      return card('🗑', '已撤回', 'grey', text, null)
    case 'confirmed':
      return card('✓', '已确认', 'green', text, id)
    case 'rejected':
      return card('✗', '已拒绝', 'grey', text, id)
    case 'linked':
      return card('🔗', '已关联', 'blue', text, null)
    default: // drafted
      return card('🧩', '技能草稿', 'amber', id.replace(/^skill:/, ''), text)
  }
}

export function cardForRead(filePath: string, workspace: string): Card | null {
  const prefix = `${workspace}/skills/`
  if (!filePath.startsWith(prefix)) return null
  const parts = filePath.slice(prefix.length).split('/')
  let name: string | null = null
  if (parts.length === 2 && parts[0] === 'builtin' && parts[1].endsWith('.md')) name = parts[1].slice(0, -3)
  else if (parts.length === 2 && parts[1] === 'SKILL.md' && parts[0] !== 'builtin') name = parts[0]
  else if (parts.length === 1 && parts[0].endsWith('.md')) name = parts[0].slice(0, -3)
  if (name === null || name === '' || name.startsWith('_')) return null
  return skill(name)
}

function field(value: unknown, key: string): string {
  const v = typeof value === 'object' && value !== null ? (value as Record<string, unknown>)[key] : undefined
  return typeof v === 'string' ? v : ''
}

export function cardForCall(call: CallLike, workspace: string, marks: ReadonlyMap<string, WriteMark>): Card | null {
  if (call.isRunning || call.isErrored || call.isInterrupted) return null
  if (call.tool === 'Bash') {
    const mark = call.tool_use_id !== undefined ? marks.get(call.tool_use_id) : undefined
    return cardForBash(field(call.input, 'command'), field(call.output, 'stdout'), mark)
  }
  if (call.tool === 'Read') return cardForRead(field(call.input, 'file_path'), workspace)
  return null
}
