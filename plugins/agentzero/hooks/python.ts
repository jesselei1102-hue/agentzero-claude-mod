export const PYTHON_CANDIDATES: readonly string[] = [
  'python3',
  'python',
  '/usr/bin/python3',
  '/opt/homebrew/bin/python3',
  '/usr/local/bin/python3',
  '/Library/Frameworks/Python.framework/Versions/Current/bin/python3',
]

export const PYTHON_PROBE = 'import sys, yaml; sys.exit(sys.version_info < (3, 11))'

export async function findPython(
  run: (argv: string[]) => Promise<{ exitCode: number }>,
): Promise<string | null> {
  for (const candidate of PYTHON_CANDIDATES) {
    try {
      if ((await run([candidate, '-c', PYTHON_PROBE])).exitCode === 0) return candidate
    } catch {
      // a candidate that cannot start is a candidate that failed
    }
  }
  return null
}
