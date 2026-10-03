export type RememberCall = {
  cd: string | null
  prefix: string[]
  sentence: string
  said: string
  factKey?: string
  scope?: string
  tags: string[]
  sourceRun?: string
}

export type RememberParse =
  | { kind: 'none' }
  | { kind: 'unreadable' }
  | { kind: 'remember'; call: RememberCall }

type Token = { text: string; op: boolean }

// POSIX-ish words. An unquoted `&&` is an operator token; any other shell
// operator, an expansion ($, backtick) or an unbalanced quote is refused.
function tokenize(command: string): Token[] | null {
  const tokens: Token[] = []
  let cur = ''
  let inWord = false
  const push = () => {
    if (inWord) tokens.push({ text: cur, op: false })
    cur = ''
    inWord = false
  }
  let i = 0
  while (i < command.length) {
    const c = command[i]
    if (c === ' ' || c === '\t') {
      push()
      i++
    } else if (c === "'") {
      const end = command.indexOf("'", i + 1)
      if (end < 0) return null
      cur += command.slice(i + 1, end)
      inWord = true
      i = end + 1
    } else if (c === '"') {
      i++
      let closed = false
      while (i < command.length) {
        const d = command[i]
        if (d === '"') {
          closed = true
          i++
          break
        }
        if (d === '$' || d === '`') return null
        if (d === '\\') {
          const n = command[i + 1]
          if (n === undefined) return null
          if (n === '"' || n === '\\' || n === '$' || n === '`') cur += n
          else if (n !== '\n') cur += '\\' + n
          i += 2
          continue
        }
        cur += d
        i++
      }
      if (!closed) return null
      inWord = true
    } else if (c === '\\') {
      const n = command[i + 1]
      if (n === undefined) return null
      if (n !== '\n') {
        cur += n
        inWord = true
      }
      i += 2
    } else if (c === '$' || c === '`') {
      return null
    } else if (c === '&' && command[i + 1] === '&') {
      push()
      tokens.push({ text: '&&', op: true })
      i += 2
    } else if (c === '&' || c === ';' || c === '|' || c === '<' || c === '>' || c === '(' || c === ')' || c === '\n' || c === '\r') {
      return null
    } else {
      cur += c
      inWord = true
      i++
    }
  }
  push()
  return tokens
}

export function splitWords(command: string): string[] | null {
  const tokens = tokenize(command)
  return tokens === null ? null : tokens.map(t => t.text)
}

// JS \s already covers U+00A0, U+3000, U+2028/9 and the U+2000 block.
const UNICODE_SPACE = /\s+/g

export function normalizeSpace(text: string): string {
  return text.replace(UNICODE_SPACE, ' ').trim()
}

export function saidFound(said: string, prompts: readonly string[]): boolean {
  const needle = normalizeSpace(said)
  if (needle === '') return false
  return prompts.some(p => normalizeSpace(p).includes(needle))
}

const VALUE_FLAGS = new Set(['--said', '--fact-key', '--scope', '--tag', '--source-run'])
const ENV_ASSIGN = /^[A-Za-z_][A-Za-z0-9_]*=/
const REMEMBER_RAW = /\bmemory\s+remember\b/

function validPrefix(prefix: string[]): boolean {
  if (prefix.length < 2 || prefix[prefix.length - 1] !== 'memory') return false
  const words = prefix.slice(0, -1)
  let k = 0
  while (k < words.length && ENV_ASSIGN.test(words[k])) k++
  const rest = words.slice(k)
  if (rest.length === 1) return /(^|\/)a0$/.test(rest[0])
  if (rest.length === 2 && rest[1] === '-m') return /(^|\/)python[0-9.]*$/.test(rest[0])
  return false
}

export function parseRemember(command: string): RememberParse {
  const tokens = tokenize(command)
  if (tokens === null) return REMEMBER_RAW.test(command) ? { kind: 'unreadable' } : { kind: 'none' }

  const at = tokens.findIndex(
    (t, i) => i > 0 && !t.op && t.text === 'remember' && !tokens[i - 1].op && tokens[i - 1].text === 'memory',
  )
  if (at < 0) {
    // `sh -c "… memory remember …"` hides the command in one word; a commit message that
    // merely mentions it does not run it.
    const hidden = tokens.some(
      (t, i) => REMEMBER_RAW.test(t.text) && i > 0 && /^(-[a-z]*c|eval)$/.test(tokens[i - 1].text),
    )
    return hidden ? { kind: 'unreadable' } : { kind: 'none' }
  }

  const segments: Token[][] = [[]]
  for (const t of tokens) {
    if (t.op) segments.push([])
    else segments[segments.length - 1].push(t)
  }
  let cd: string | null = null
  let words: string[]
  if (segments.length === 1) {
    words = segments[0].map(t => t.text)
  } else if (segments.length === 2 && segments[0].length === 2 && segments[0][0].text === 'cd') {
    cd = segments[0][1].text
    words = segments[1].map(t => t.text)
  } else {
    return { kind: 'unreadable' }
  }

  const r = words.indexOf('remember')
  if (r < 1 || words[r - 1] !== 'memory') return { kind: 'unreadable' }
  const prefix = words.slice(0, r)
  if (!validPrefix(prefix)) return { kind: 'unreadable' }

  const call: RememberCall = { cd, prefix, sentence: '', said: '', tags: [] }
  let sentence: string | undefined
  let said: string | undefined
  let sawSaid = false
  const args = words.slice(r + 1)
  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    if (a.startsWith('--')) {
      let flag = a
      let value: string | undefined
      const eq = a.indexOf('=')
      if (eq > 0) {
        flag = a.slice(0, eq)
        value = a.slice(eq + 1)
      }
      if (!VALUE_FLAGS.has(flag)) return { kind: 'unreadable' }
      if (value === undefined) {
        if (i + 1 >= args.length) return { kind: 'unreadable' }
        value = args[++i]
      }
      if (flag === '--said') {
        sawSaid = true
        said = value
      } else if (flag === '--fact-key') call.factKey = value
      else if (flag === '--scope') call.scope = value
      else if (flag === '--tag') call.tags.push(value)
      else call.sourceRun = value
    } else if (sentence === undefined) {
      sentence = a
    } else {
      return { kind: 'unreadable' }
    }
  }
  // Without --said there is nothing to check; the kernel refuses it itself.
  if (!sawSaid) return { kind: 'none' }
  if (sentence === undefined || said === undefined) return { kind: 'unreadable' }
  call.sentence = sentence
  call.said = said
  return { kind: 'remember', call }
}

function quote(word: string): string {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(word)) return word
  return "'" + word.replace(/'/g, "'\\''") + "'"
}

export function proposeCommand(call: RememberCall): string {
  const parts = [...call.prefix, 'propose', 'fact', call.sentence]
  if (call.factKey !== undefined) parts.push('--fact-key', call.factKey)
  if (call.scope !== undefined) parts.push('--scope', call.scope)
  for (const tag of call.tags) parts.push('--tag', tag)
  if (call.sourceRun !== undefined) parts.push('--source-run', call.sourceRun)
  const body = parts.map(quote).join(' ')
  return call.cd === null ? body : `cd ${quote(call.cd)} && ${body}`
}
