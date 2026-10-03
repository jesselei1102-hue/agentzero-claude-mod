import type { Register } from 'claude-code'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    $.ui.status('AgentZero plugin loaded: ' + $.plugin.root)
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    $.ui.toast('origin: ' + e.origin.kind)
    return next(e)
  })
}
