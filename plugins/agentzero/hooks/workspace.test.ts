import { expect, test } from 'claude-code/testing'
import { findWorkspace } from './workspace'

const has = (...paths: string[]) => async (p: string) => paths.includes(p)

test('findWorkspace finds the folder above', async () => {
  expect(await findWorkspace('/w/a/b', has('/w/System.md', '/w/memory'))).toBe('/w')
})

test('findWorkspace returns null with none', async () => {
  expect(await findWorkspace('/x/y', has())).toBeNull()
})

test('findWorkspace skips a template folder beside src/adapter', async () => {
  const exists = has('/repo/template/System.md', '/repo/template/memory', '/repo/src/adapter')
  expect(await findWorkspace('/repo/template/work', exists)).toBeNull()
})

test('findWorkspace takes the nearest workspace and needs both System.md and memory', async () => {
  expect(await findWorkspace('/w/a', has('/w/System.md'))).toBeNull()
  const nested = has('/w/System.md', '/w/memory', '/w/a/System.md', '/w/a/memory')
  expect(await findWorkspace('/w/a/b', nested)).toBe('/w/a')
})

test('findWorkspace accepts a folder named template with no src/adapter beside it', async () => {
  expect(await findWorkspace('/t/template', has('/t/template/System.md', '/t/template/memory'))).toBe('/t/template')
})
