import type { WriteMark } from './session'
import { CARD_DETAIL_PX, cutToWidth, textWidth } from './svg'
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

const ON_FILE = 'Already on record'

// The quote is cut so "✓ checked" always fits on the card's detail line.
const QUOTE_FRAME = 'Your words: “” ✓ checked'

function cutQuote(said: string): string {
  return cutToWidth(said, CARD_DETAIL_PX - textWidth(QUOTE_FRAME, 12.5), 12.5)
}

function card(icon: string, label: string, tone: Tone, title: string, detail: string | null, outline = false): Card {
  return { icon, label, tone, title, detail, outline }
}

const remembered = (title: string, detail: string, outline = false) => card('📌', 'Remembered', 'green', title, detail, outline)
const waiting = (title: string, detail: string) => card('⏳', 'Waiting for you', 'amber', title, detail)
const skill = (name: string) => card('🧭', 'Skill used', 'blue', name, null)

export function cardForBash(command: string, stdout: string, mark: WriteMark | undefined): Card | null {
  // A command the word check marked is a remember even when it could not be read.
  const c = a0Command(command) ?? (mark !== undefined ? { module: 'memory' as const, sub: 'remember', args: [] } : null)
  if (c === null) return null
  if (c.module === 'skills' && c.sub === 'run') return skill(c.args[0] ?? '')
  if (!writes(c)) return null

  const first = stdout.split('\n')[0].trimEnd()
  const declared = DECLARED.exec(first)
  if (declared) return card('📚', 'Knowledge added', 'blue', declared[4], declared[1] === 'declared' ? declared[3] : ON_FILE)
  const onRecord = ON_RECORD.exec(first)
  if (onRecord) return onRecord[1] === 'active' ? remembered(onRecord[3], ON_FILE) : waiting(onRecord[3], ON_FILE)
  const m = LINE.exec(first)
  if (!m) return null
  const [, verb, id, text] = m
  switch (verb) {
    case 'remembered': {
      const parsed = parseRemember(command)
      if (mark === 'unchecked' || parsed.kind !== 'remember') return remembered(text, 'Quote not checked', true)
      return remembered(text, `Your words: “${cutQuote(parsed.call.said)}” ✓ checked`)
    }
    case 'already remembered':
      return remembered(text, ON_FILE)
    case 'proposed':
      if (mark === 'rewritten') return waiting(text, 'Not in your words, so saved as a proposal')
      return waiting(text, c.sub === 'remember' ? 'Says more than your words, so saved as a proposal' : 'Inferred by the assistant')
    case 'forgot':
      return card('🗑', 'Forgotten', 'grey', text, null)
    case 'confirmed':
      return card('✓', 'Confirmed', 'green', text, id)
    case 'rejected':
      return card('✗', 'Rejected', 'grey', text, id)
    case 'linked':
      return card('🔗', 'Linked', 'blue', text, null)
    default: // drafted
      return card('🧩', 'Skill draft', 'amber', id.replace(/^skill:/, ''), text)
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

// Agents often read a skill through the shell (AgentZero #92): `cat skills/builtin/analyze.md`.
const READ_VERB = /(^|[\s;&|(])(cat|head|tail|less|more|sed|bat)\s/
const SKILL_PATH = /(?:^|[\s'"=])((?:\/[^\s'"]*\/)?skills\/(?:builtin\/([A-Za-z0-9][\w-]*)\.md|([A-Za-z0-9][\w-]*)\/SKILL\.md|([A-Za-z0-9][\w-]*)\.md))(?=$|[\s'";|&)])/g

export function skillsReadByShell(command: string, workspace: string): string[] {
  if (!READ_VERB.test(command)) return []
  const names: string[] = []
  for (const m of command.matchAll(SKILL_PATH)) {
    const path = m[1]
    if (path.startsWith('/') && !path.startsWith(`${workspace}/skills/`)) continue
    const name = m[2] ?? m[3] ?? m[4]
    if (m[3] === 'builtin') continue
    if (!names.includes(name)) names.push(name)
  }
  return names
}

function field(value: unknown, key: string): string {
  const v = typeof value === 'object' && value !== null ? (value as Record<string, unknown>)[key] : undefined
  return typeof v === 'string' ? v : ''
}

// What a call in a folded group shows. The desktop keeps a group the engine drew while a call
// ran, so a call recognisable from its input alone is drawn by the plugin from the start:
// a placeholder while it runs, its card when it ends, "没有记下" when it fails.
export function groupCard(call: CallLike, workspace: string, marks: ReadonlyMap<string, WriteMark>): Card | null {
  if (call.tool === 'Read') return call.isErrored ? null : cardForRead(field(call.input, 'file_path'), workspace)
  if (call.tool !== 'Bash') return null
  const command = field(call.input, 'command')
  const read = skillsReadByShell(command, workspace)
  const c = a0Command(command)
  const isSkillRun = c !== null && c.module === 'skills' && c.sub === 'run'
  if (!isMemoryWrite(command) && !isSkillRun) return read.length > 0 && !call.isErrored ? skill(read.join(', ')) : null
  if (isSkillRun) return call.isErrored ? null : skill(c.args[0] ?? '')
  const parsed = parseRemember(command)
  const title = parsed.kind === 'remember' ? parsed.call.sentence : `${(c as A0Command).module} ${(c as A0Command).sub}`
  if (call.isRunning) return card('⏳', 'Recording', 'grey', title, null)
  if (call.isErrored || call.isInterrupted) return card('✗', 'Not recorded', 'grey', title, null)
  return cardForCall(call, workspace, marks) ?? card('✓', 'Done', 'grey', title, null)
}

export function cardForCall(call: CallLike, workspace: string, marks: ReadonlyMap<string, WriteMark>): Card | null {
  if (call.isRunning || call.isErrored || call.isInterrupted) return null
  if (call.tool === 'Bash') {
    const mark = call.tool_use_id !== undefined ? marks.get(call.tool_use_id) : undefined
    const command = field(call.input, 'command')
    const written = cardForBash(command, field(call.output, 'stdout'), mark)
    if (written !== null) return written
    const read = skillsReadByShell(command, workspace)
    return read.length > 0 ? skill(read.join(', ')) : null
  }
  if (call.tool === 'Read') return cardForRead(field(call.input, 'file_path'), workspace)
  return null
}
