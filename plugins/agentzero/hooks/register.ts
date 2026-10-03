import type { Register } from 'claude-code'
import { registerHotSet } from './feature-hotset'
import { registerSaidCheck } from './feature-said'

export const register: Register = on => {
  registerHotSet(on)
  registerSaidCheck(on)
}
