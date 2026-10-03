export const SIX_HOURS_MS = 21_600_000

export type InjectState = { lastAt: number | null; resetSince: boolean }

export function needsHotSet(s: InjectState, now: number): boolean {
  return s.lastAt === null || s.resetSince || now - s.lastAt > SIX_HOURS_MS
}

export function hintsFrom(prompt: string): string {
  const flat = prompt.replace(/\r\n|[\r\n]/g, ' ')
  return Array.from(flat).slice(0, 200).join('')
}

export function hotSetContext(output: string, localTime: string): string {
  return [
    `AgentZero hot set, loaded by the Claude Code plugin at ${localTime}.`,
    'Rule 3 is done for this session: do not run hot-set again unless your context is compacted or cleared.',
    '',
    output,
  ].join('\n')
}
