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

See `plugins/agentzero/hooks/smoke.test.ts` for working examples of: a session.start test with status capture, a prompt.submit test with toast capture, and a `tool.call` for `Bash` test.
