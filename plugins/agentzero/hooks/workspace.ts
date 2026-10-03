export type Probe = (path: string) => Promise<boolean>

function parentOf(dir: string): string | null {
  if (dir === '/' || dir === '') return null
  const cut = dir.lastIndexOf('/')
  if (cut < 0) return null
  return cut === 0 ? '/' : dir.slice(0, cut)
}

function join(dir: string, name: string): string {
  return dir === '/' ? '/' + name : dir + '/' + name
}

// A workspace holds System.md and memory/. A folder named `template` whose parent
// holds src/adapter is a framework's template, not a workspace (SETTLED #86).
export async function findWorkspace(start: string, exists: Probe): Promise<string | null> {
  let dir: string | null = start
  while (dir !== null) {
    if ((await exists(join(dir, 'System.md'))) && (await exists(join(dir, 'memory')))) {
      const parent = parentOf(dir)
      const isTemplate =
        dir.slice(dir.lastIndexOf('/') + 1) === 'template' &&
        parent !== null &&
        (await exists(join(join(parent, 'src'), 'adapter')))
      if (!isTemplate) return dir
    }
    dir = parentOf(dir)
  }
  return null
}
