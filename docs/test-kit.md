# Test kit: how a hooks test is written

Run: `claude plugin test plugins/agentzero` (every `*.test.ts` under the folder). Validate: `claude plugin validate plugins/agentzero`.

```ts
import { expect, test, mock } from 'claude-code/testing'

test('name', async ($, on) => { ... })
```

- `$` is the engine's own. A test raises an event by calling it: `$.session.start({ cwd, surface: 'terminal', isInteractive: true })`, `$.prompt.submit({ text, origin: { kind: 'composer' }, wait: false })`, `$.tool.call({ tool: 'Bash', command })`, `$.command.run(...)`.
- `on(...)` registers hooks **beneath** the plugin. They stand in for the engine and answer for it. Nothing else answers: an event no test hook answers fails with `no implementation for <event>`.
  - Answer the event the test raises: `on('session.start', async (_$, e) => ({ cwd: e.cwd }))`, `on('prompt.submit', async (_$, e) => ({ text: e.text }))`.
  - Capture a plugin's side effects by answering them without calling `next`: `on('ui.status', async (_$, e) => { seen.push(e.text) })`, same for `ui.toast`.
  - Mock `$.process.run`: `on('process.run', async (_$, e) => ({ ... }))`; `e.argv` and `e.init` are what the plugin passed.
  - Engine tool: `on('tool.call', { tool: 'Bash' }, async (_$, e) => ({ result: { stdout: 'ok', stderr: '' } }))`; `e.command` is what reached the tool after the plugin's rewrite. A plugin's `{ deny }` shows as `out.deny`.
- Mocked clock: `const clock = mock.clock(on, { now: 0 })`, then `await clock.advance(ms)`; `$.clock.now()` reads it. Mock store and env: `mock.store(on, {...})`, `mock.env(on, {...})`.
- Checks: `expect(x).toBe/toEqual/toBeUndefined/...`.
- Tests have no fs, network or process of their own: everything outside is a mocked `on` hook.
- `$.plugin.root` in a test is the plugin's folder.

Working examples: `plugins/agentzero/hooks/feature-hotset.test.ts` with its stand-in engine `plugins/agentzero/hooks/test-world.ts` (session id/root, fs.stat, process.run, ui.status/toast, mocked clock). An early smoke test also showed a `tool.call` for `Bash`:

```ts
test('tool.call for Bash reaches the engine bottom unchanged', async ($, on) => {
  let seen = ''
  on('tool.call', { tool: 'Bash' }, async (_$, e) => { seen = e.command; return { result: { stdout: 'ok', stderr: '' } } })
  const out = await $.tool.call({ tool: 'Bash', command: 'echo hi' })
  expect(seen).toBe('echo hi')
  expect(out.deny).toBeUndefined()
})
```

## Rules the validator and engine enforce

- `$` is never passed across an import. A helper in another file cannot take `$`; pass closures made at the call site (`() => $.session.root()`) or keep the helper in the same file. `on` may be passed (`registerHotSet(on)`).
- Bottom hooks answer a call on `$` with `{ value }` (e.g. `session.id`, `fs.stat`, `process.run`) or `{ deny: 'reason' }` (the plugin's `await` rejects with that message). An event hook (`session.compact`) answers its result type: `{ messages: [oneMessage] }` (empty is refused).
- A `/clear` ends the session (`session.end`, `reason: 'clear'`) and the process goes on under a new session id with no `session.start`.
- Do not write `\uXXXX` escapes in a regex character class: this parser rejects them. `\s` already covers U+00A0 and U+3000.
